# The tells: what makes a 3D model look generated

Generated geometry fails in predictable ways. Most of it comes from three sources, and each leaves its own fingerprints.

## 1. Image or text to 3D generators

Tools that turn a picture or prompt into a mesh (Meshy, Tripo, Rodin, Hunyuan3D, TRELLIS and similar) reconstruct a surface from a volume. The result looks fine in a thumbnail and falls apart up close.

| Tell | What you see | Why it happens |
|---|---|---|
| **Triangle soup** | Nearly 100% triangles of similar size, most vertices joining 6 edges, no edge loops following the form | The surface is extracted from a voxel or field grid (marching cubes), not modeled |
| **Density ignores detail** | A flat panel has as many triangles as a detailed buckle; a crate with 50,000 triangles | Uniform extraction resolution |
| **Mushy hard edges** | Corners are rounded and lumpy, flat faces wobble, stair-step ridges | The grid can't represent a crisp edge |
| **Melted, fused parts** | Straps, fingers, handles and gaps merge into blobs; thin parts get holes or vanish | Everything is one continuous surface |
| **Invented back side** | The side the input image didn't show is vague, asymmetric or wrong | The model guesses unseen geometry |
| **Geometry defects** | Non-manifold edges, duplicate vertices, inward normals, fragments floating inside the mesh | Reconstruction and export artifacts |
| **Baked lighting** | Shadows and highlights painted into the color texture | The texture is projected from a lit photo |
| **Shredded UVs** | One texture atlas cut into hundreds of tiny islands | Automatic atlas packing |
| **Gibberish detail** | Text, logos and panel markings that almost read but don't | Same as AI images |
| **Anatomy errors** | Wrong finger counts, merged or twisted limbs | Same as AI images |
| **Export names** | `mesh_0`, `material_0`, `texture_0`, one object, no modifiers, arbitrary scale | Straight from the exporter |

## 2. Scenes built by AI-written scripts

When a language model writes Blender Python to build a model, the mesh is clean but the *construction* gives it away.

| Tell | What you see |
|---|---|
| **Box kitbashing** | Most parts are untouched 8-vertex cubes and default cylinders |
| **Detail faked with loose pieces** | Hundreds or thousands of separate boxes packed inside one object, instead of modeled insets and panels |
| **Razor edges** | No bevels anywhere, so edges don't catch light |
| **Overlaps instead of joins** | Parts sit inside each other with no transition |
| **No UVs** | Only flat color materials; nothing can be textured |
| **Unapplied scale** | Objects scaled non-uniformly, so bevels and modifiers distort |
| **Leftover scripts** | The generator code still sits in the file's text blocks |
| **Over-specified names, under-specified shapes** | Names like `IR_LED_850nm` on a plain box |
| **Self-certifying audits** | Embedded reports saying "0 intersections" that only test what the script tests, not how it looks |

## 3. AI in CAD (Fusion and similar)

| Tell | What you see |
|---|---|
| **Unconstrained sketches** | Blue sketch lines at absolute coordinates; changing one size breaks the part |
| **No design intent** | No named parameters; features don't reference each other |
| **Missing manufacturing features** | No drafts, fillets or chamfers; walls of random thickness |
| **Overlapping or non-functional features** | Snap fits and bosses that intersect or do nothing |
| **Mesh bodies** | Triangulated meshes imported as bodies instead of solid geometry |

## What a human-made model has instead

- **Edge flow** that follows the form: quads, loops around openings, density where detail is.
- **Broken edges**: small bevels, fillets or chamfers everywhere a real object would have them.
- **Intent**: parts that are modeled as separate pieces where real objects have separate pieces, joined where they're joined.
- **Clean data**: applied transforms, outward normals, unwrapped UVs, meaningful names.
- **Variation**: wear, small asymmetries and texture detail that have a reason to be there.

## Caveat

None of these tells proves anything on its own. Game assets are often fully triangulated, photogrammetry scans are dense, and fast blockouts are made of boxes. Treat the checks as a list of things to improve, not as a verdict.

## Sources

- [Neural4D: fixing bad topology in AI 3D models](https://blog.neural4d.com/user-guide/blender-retopology-ai-3d-models/)
- [Hitem3D: why AI 3D meshes get weird shapes](https://www.hitem3d.ai/ai-faq/why-3d-mesh-3d-model-is-weird-shapes-in-3d-generation)
- [SF3D paper: marching-cubes artifacts, baked lighting, UV unwrapping](https://arxiv.org/html/2408.00653v1)
- [Meta 3D AssetGen paper](https://arxiv.org/pdf/2407.02445)
- [Creative Bloq: how to spot AI-generated 3D models](https://creativebloq.com/ai/this-is-how-to-spot-ai-generated-3d-models)
- [Game Developer: how devs can spot AI-generated 3D models](https://www.gamedeveloper.com/art/how-devs-can-spot-ai-generated-3d-models)
- [Atomic Object: Blender scripting with AI](https://spin.atomicobject.com/blender-scripting-with-ai/)
- [All3DP: testing text-to-CAD](https://all3dp.com/2/ai-cad-model-generator-cadscribe/)
