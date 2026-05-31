// mp_shim.cpp
//
// Thin C ABI shim over meshoptimizer for the Blender "Meshlet Preview" addon.
// It runs the whole pipeline in one call (build meshlets -> per-meshlet bounds
// and analyzers -> global stats) and returns flat heap arrays that the Python
// ctypes layer copies out and then releases with mp_free_result().
//
// Everything is plain C linkage with pointer outputs (no struct-by-value
// returns) so the ctypes binding stays trivial and ABI-robust.

#include "meshoptimizer/src/meshoptimizer.h"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <vector>

// Export the public C entry points. MSVC exports nothing from a DLL by default;
// on macOS/Linux default visibility already exports them.
#if defined(_WIN32)
#define MP_EXPORT __declspec(dllexport)
#else
#define MP_EXPORT
#endif

extern "C" {

struct mp_result {
	// Number of meshlets produced.
	unsigned int meshlet_count;
	// Number of triangles across all meshlets (drives the draw buffers below).
	unsigned int triangle_count;

	// Per-meshlet arrays (length == meshlet_count).
	unsigned int* vertex_counts;   // vertices used by the meshlet
	unsigned int* triangle_counts; // triangles in the meshlet
	float* cone_cutoff;            // sin(angle/2); ~0 tight (good), ~1 wide/uncullable (bad)
	float* cone_axis;              // meshlet_count * 3
	float* center;                 // meshlet_count * 3 (bounding sphere, object space)
	float* radius;                 // meshlet_count
	float* acmr;                   // per-meshlet average cache miss ratio
	float* overdraw;               // per-meshlet overdraw ratio (>= 1.0)
	unsigned int* degenerate_counts; // per-meshlet count of degenerate/sliver triangles
	float* compactness;            // per-meshlet spatial compactness in [0,1] (1 = tight)

	// Draw buffers (length == triangle_count and triangle_count*3).
	unsigned int* tri_meshlet;     // meshlet id for each output triangle
	unsigned int* tri_indices;     // 3 original vertex indices per triangle
	unsigned char* tri_degenerate; // 1 if the output triangle is degenerate/sliver

	// Global statistics over the (optionally reordered) full index buffer.
	float global_acmr;
	float global_atvr;
	float global_overdraw;
	float global_overfetch;
	unsigned int total_degenerate; // total degenerate/sliver triangles
};

MP_EXPORT void mp_free_result(mp_result* r);

static unsigned int* alloc_uint(size_t n) {
	return (unsigned int*)std::malloc(n * sizeof(unsigned int));
}
static float* alloc_float(size_t n) {
	return (float*)std::malloc(n * sizeof(float));
}

// Scale-invariant triangle quality: 1 for equilateral, ~0 for a sliver or a
// zero-area (degenerate) triangle. q = 4*sqrt(3)*area / (sum of squared edges).
static float triangle_quality(const float* p0, const float* p1, const float* p2,
                              float* out_area) {
	float e0[3] = {p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]};
	float e1[3] = {p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]};
	float e2[3] = {p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]};
	float cx = e0[1] * e1[2] - e0[2] * e1[1];
	float cy = e0[2] * e1[0] - e0[0] * e1[2];
	float cz = e0[0] * e1[1] - e0[1] * e1[0];
	float area = 0.5f * std::sqrt(cx * cx + cy * cy + cz * cz);
	float sumsq = (e0[0] * e0[0] + e0[1] * e0[1] + e0[2] * e0[2]) +
	              (e1[0] * e1[0] + e1[1] * e1[1] + e1[2] * e1[2]) +
	              (e2[0] * e2[0] + e2[1] * e2[1] + e2[2] * e2[2]);
	if (out_area)
		*out_area = area;
	if (sumsq <= 0.0f)
		return 0.0f;
	return (6.9282032302755f * area) / sumsq; // 4*sqrt(3) = 6.9282032...
}

// positions: vertex_count * 3 floats (object space, tightly packed)
// indices:   index_count uints (triangle list)
// Returns NULL on allocation failure or degenerate input.
MP_EXPORT mp_result* mp_build(
    const float* positions, unsigned int vertex_count,
    const unsigned int* indices, unsigned int index_count,
    unsigned int max_vertices, unsigned int max_triangles, float cone_weight,
    int optimize_first, float sliver_quality)
{
	if (!positions || !indices || index_count < 3 || vertex_count == 0)
		return NULL;

	const size_t vstride = sizeof(float) * 3;

	// Optionally reorder indices for vertex-cache locality before clustering;
	// this is also what makes the global ACMR/overdraw numbers meaningful.
	std::vector<unsigned int> work(indices, indices + index_count);
	if (optimize_first) {
		std::vector<unsigned int> opt(index_count);
		meshopt_optimizeVertexCache(opt.data(), work.data(), index_count, vertex_count);
		meshopt_optimizeOverdraw(work.data(), opt.data(), index_count,
		                         positions, vertex_count, vstride, 1.05f);
	}

	const size_t max_meshlets =
	    meshopt_buildMeshletsBound(index_count, max_vertices, max_triangles);
	if (max_meshlets == 0)
		return NULL;

	std::vector<meshopt_Meshlet> meshlets(max_meshlets);
	std::vector<unsigned int> meshlet_vertices(max_meshlets * max_vertices);
	std::vector<unsigned char> meshlet_triangles(max_meshlets * max_triangles * 3);

	const size_t count = meshopt_buildMeshlets(
	    meshlets.data(), meshlet_vertices.data(), meshlet_triangles.data(),
	    work.data(), index_count, positions, vertex_count, vstride,
	    max_vertices, max_triangles, cone_weight);
	if (count == 0)
		return NULL;

	// Total triangles across the produced meshlets.
	size_t total_tris = 0;
	for (size_t i = 0; i < count; ++i)
		total_tris += meshlets[i].triangle_count;

	mp_result* r = (mp_result*)std::calloc(1, sizeof(mp_result));
	if (!r)
		return NULL;

	r->meshlet_count = (unsigned int)count;
	r->triangle_count = (unsigned int)total_tris;
	r->vertex_counts = alloc_uint(count);
	r->triangle_counts = alloc_uint(count);
	r->cone_cutoff = alloc_float(count);
	r->cone_axis = alloc_float(count * 3);
	r->center = alloc_float(count * 3);
	r->radius = alloc_float(count);
	r->acmr = alloc_float(count);
	r->overdraw = alloc_float(count);
	r->degenerate_counts = alloc_uint(count);
	r->compactness = alloc_float(count);
	r->tri_meshlet = alloc_uint(total_tris);
	r->tri_indices = alloc_uint(total_tris * 3);
	r->tri_degenerate = (unsigned char*)std::malloc(total_tris);

	if (!r->vertex_counts || !r->triangle_counts || !r->cone_cutoff ||
	    !r->cone_axis || !r->center || !r->radius || !r->acmr ||
	    !r->overdraw || !r->degenerate_counts || !r->compactness ||
	    !r->tri_meshlet || !r->tri_indices || !r->tri_degenerate) {
		mp_free_result(r);
		return NULL;
	}

	if (sliver_quality < 0.0f)  // 0 = detection off; negatives clamped
		sliver_quality = 0.0f;
	r->total_degenerate = 0;

	// Scratch buffer holding one meshlet's triangles expressed as original
	// vertex indices; reused across meshlets for the per-meshlet analyzers.
	std::vector<unsigned int> local(max_triangles * 3);

	size_t tri_cursor = 0;
	for (size_t m = 0; m < count; ++m) {
		const meshopt_Meshlet& ml = meshlets[m];
		const unsigned int* mv = &meshlet_vertices[ml.vertex_offset];
		const unsigned char* mt = &meshlet_triangles[ml.triangle_offset];

		r->vertex_counts[m] = ml.vertex_count;
		r->triangle_counts[m] = ml.triangle_count;

		// Resolve local micro-indices to original vertex indices, and flag
		// degenerate/sliver triangles + accumulate area for compactness.
		local.resize(ml.triangle_count * 3);
		unsigned int degenerate = 0;
		float area_sum = 0.0f;
		for (unsigned int t = 0; t < ml.triangle_count; ++t) {
			unsigned int a = mv[mt[t * 3 + 0]];
			unsigned int b = mv[mt[t * 3 + 1]];
			unsigned int c = mv[mt[t * 3 + 2]];
			local[t * 3 + 0] = a;
			local[t * 3 + 1] = b;
			local[t * 3 + 2] = c;

			float area = 0.0f;
			float q = triangle_quality(&positions[a * 3], &positions[b * 3],
			                           &positions[c * 3], &area);
			area_sum += area;
			unsigned char bad = (q < sliver_quality) ? 1 : 0;
			degenerate += bad;

			r->tri_meshlet[tri_cursor] = (unsigned int)m;
			r->tri_indices[tri_cursor * 3 + 0] = a;
			r->tri_indices[tri_cursor * 3 + 1] = b;
			r->tri_indices[tri_cursor * 3 + 2] = c;
			r->tri_degenerate[tri_cursor] = bad;
			++tri_cursor;
		}
		r->degenerate_counts[m] = degenerate;
		r->total_degenerate += degenerate;

		meshopt_Bounds b = meshopt_computeMeshletBounds(
		    mv, mt, ml.triangle_count, positions, vertex_count, vstride);
		r->cone_cutoff[m] = b.cone_cutoff;
		r->cone_axis[m * 3 + 0] = b.cone_axis[0];
		r->cone_axis[m * 3 + 1] = b.cone_axis[1];
		r->cone_axis[m * 3 + 2] = b.cone_axis[2];
		r->center[m * 3 + 0] = b.center[0];
		r->center[m * 3 + 1] = b.center[1];
		r->center[m * 3 + 2] = b.center[2];
		r->radius[m] = b.radius;

		// Compactness: a flat compact patch has area ~ pi*r^2, so
		// sqrt(area/pi)/radius ~ 1; a stringy/scattered meshlet gives << 1.
		float comp = 0.0f;
		if (b.radius > 1e-8f)
			comp = std::sqrt(area_sum / 3.14159265f) / b.radius;
		r->compactness[m] = comp > 1.0f ? 1.0f : comp;

		meshopt_VertexCacheStatistics vcs = meshopt_analyzeVertexCache(
		    local.data(), ml.triangle_count * 3, vertex_count, 16, 0, 0);
		r->acmr[m] = vcs.acmr;

		meshopt_OverdrawStatistics ods = meshopt_analyzeOverdraw(
		    local.data(), ml.triangle_count * 3, positions, vertex_count, vstride);
		r->overdraw[m] = ods.overdraw;
	}

	meshopt_VertexCacheStatistics gvcs =
	    meshopt_analyzeVertexCache(work.data(), index_count, vertex_count, 16, 0, 0);
	r->global_acmr = gvcs.acmr;
	r->global_atvr = gvcs.atvr;

	meshopt_OverdrawStatistics gods =
	    meshopt_analyzeOverdraw(work.data(), index_count, positions, vertex_count, vstride);
	r->global_overdraw = gods.overdraw;

	meshopt_VertexFetchStatistics gvfs =
	    meshopt_analyzeVertexFetch(work.data(), index_count, vertex_count, vstride);
	r->global_overfetch = gvfs.overfetch;

	return r;
}

MP_EXPORT void mp_free_result(mp_result* r) {
	if (!r)
		return;
	std::free(r->vertex_counts);
	std::free(r->triangle_counts);
	std::free(r->cone_cutoff);
	std::free(r->cone_axis);
	std::free(r->center);
	std::free(r->radius);
	std::free(r->acmr);
	std::free(r->overdraw);
	std::free(r->degenerate_counts);
	std::free(r->compactness);
	std::free(r->tri_meshlet);
	std::free(r->tri_indices);
	std::free(r->tri_degenerate);
	std::free(r);
}

MP_EXPORT int mp_version(void) {
	return MESHOPTIMIZER_VERSION;
}

} // extern "C"
