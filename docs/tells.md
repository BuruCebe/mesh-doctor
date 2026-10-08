# The tells: what makes 3D work look generated

Generated 3D fails in predictable ways. Sections 1 to 3 cover where the geometry comes from; sections 4 to 6 cover everything around it: materials, lighting, camera, scene and animation. Model Doctor checks for most of these.

Every row says where it comes from. A footnote links to the published source. **(MD)** marks something we measured ourselves while calibrating Model Doctor on AI-scripted scenes and known-clean assets, or a rule of thumb from 3D practice; treat those as our observations, not established findings.

## 1. Image or text to 3D generators

Tools that turn a picture or prompt into a mesh (Meshy, Tripo and similar) predict a surface and convert it to polygons. The result looks fine in a thumbnail and falls apart up close.

| Tell | What you see | Source |
|---|---|---|
| **Triangle soup** | Dense triangles with no logical structure, scattered poles, no edge loops placed for deformation | Neural4D[^neural4d] |
| | Almost every vertex joins exactly 6 edges | (MD) |
| **Density ignores detail** | A crate with 50,000 triangles where a game crate needs about 500 | Liz Edwards in Game Developer[^gamedev] |
| **Staircase artifacts** | Stepped ridges and lumpy surfaces from Marching Cubes extraction | SF3D paper[^sf3d] |
| **Melted, welded parts** | Meshes merge into featureless blobs; limbs weld together, so the model can't be posed or animated | Liz Edwards in Game Developer[^gamedev] |
| **Asymmetry** | Objects that should be symmetrical rarely are | Liz Edwards in Game Developer[^gamedev] |
| **Geometry defects** | Non-manifold edges, holes, thousands of duplicate vertices (Meshy), inverted normals and floating fragments (Tripo) | Neural4D[^neural4d] |
| **Baked lighting** | Lighting baked into a texture projected from a 2D image | Liz Edwards in Game Developer[^gamedev]; SF3D paper[^sf3d] |
| **Jumbled UVs** | Automatically unwrapped maps that are a jumbled mess | Liz Edwards in Game Developer[^gamedev] |
| **Incoherent detail** | Close up, details look unsettling and make no sense, which also separates AI output from photogrammetry | Liz Edwards in Game Developer[^gamedev] |
| **Export names** | `mesh_0`, `material_0`, `texture_0`, one object, no modifiers | (MD) heuristic |

## 2. Scenes built by AI-written scripts

Language models can write Blender Python that builds a whole scene; research systems such as LL3M[^ll3m] do exactly this. The mesh is clean, but the *construction* gives it away.

| Tell | What you see | Source |
|---|---|---|
| **Context mistakes** | Blender is stateful: code depends on what is active or selected, and API changes between versions break scripts | Atomic Object[^atomic] |
| **Visual details need a human** | Placement and realistic touches come out wrong and are easier to fix by hand | Atomic Object[^atomic] |
| **Box kitbashing** | Most parts are untouched 8-vertex cubes and default cylinders | (MD) |
| **Detail faked with loose pieces** | Hundreds or thousands of separate boxes packed inside one object | (MD) |
| **Razor edges** | No bevels, so edges don't catch light | (MD) |
| **No UVs** | Flat color materials only; nothing can be textured | (MD) |
| **Unapplied scale** | Objects scaled non-uniformly, so bevels and modifiers distort | (MD) |
| **Leftover scripts** | The generator code still sits in the file's text blocks | (MD) |
| **Self-certifying audits** | Embedded reports saying "0 intersections" that only test what the script tests | (MD) |

## 3. AI in CAD (Fusion and similar)

| Tell | What you see | Source |
|---|---|---|
| **Absolute coordinates** | Geometry placed by coordinates instead of constrained sketch profiles | Leo AI review[^leo] |
| **Brittle models** | Looks right, but changing one dimension breaks the sketch | Leo AI review[^leo] |
| **Non-functional features** | Overlapping features, missing drafts on internal walls, snap fits that would never work | Leo AI review[^leo] |
| **Mesh bodies** | Triangulated meshes brought in as bodies instead of solid geometry | (MD) |

## 4. Materials and textures

A clean mesh still looks generated if every surface is the same flat plastic, or if the texture fights the lighting.

| Tell | What you see | Source |
|---|---|---|
| **Projected, lit textures** | One color texture projected from a 2D image, with the lighting of that image baked in | Liz Edwards in Game Developer[^gamedev]; SF3D paper[^sf3d] |
| **Color texture only** | A color map but no roughness or normal detail, so the whole surface has one sheen | (MD) |
| **Flat default materials** | One base color and one roughness value on every part; no wear, no breakup | (MD) |
| **Missing textures** | Pink or black surfaces where image files didn't come along | (MD) |

## 5. Lighting, color and camera

| Tell | What you see | Source |
|---|---|---|
| **Flat lighting** | No lights and a plain world color: no key light, no shadow shape, no separation from the background. Classic three-point lighting uses a key, a softer fill and a back light for separation | Three-point lighting[^threepoint]; (MD) for the check |
| **Harsh color** | The *Standard* view transform does no conversion beyond the display's, while *AgX* is the transform the manual describes as giving more photorealistic results | Blender Manual[^blendercm] |
| **Default camera** | The startup scene's camera angle and lens, so the shot wasn't framed on purpose | (MD) |

## 6. Scene and animation

| Tell | What you see | Source |
|---|---|---|
| **Identical clones** | Rows of copies with exactly the same rotation and scale | (MD) |
| **Unreal scale** | Scenes kilometers wide or millimeters small, which breaks light falloff, depth of field and physics | (MD) |
| **Robotic timing** | Keyframes evenly spaced with linear motion. Animators add *slow in and slow out* and vary *timing*, two of Disney's twelve principles | Twelve principles of animation[^twelve] |

## What finished work has instead

- **Edge flow**: edge loops placed on purpose, for example at joints that bend.[^neural4d]
- **Sensible density**: a crate that needs 500 triangles has about 500.[^gamedev]
- **Broken edges**: small bevels, fillets or chamfers where a real object has them. (MD)
- **Clean data**: applied transforms, outward normals, unwrapped UVs, meaningful names. (MD)
- **Materials with history**: roughness breakup, color variation, wear where hands and weather would leave it. (MD)
- **Lighting with intent**: a key light that shapes the form, fill that controls contrast, and a rim that separates the subject.[^threepoint]
- **Motion with weight**: easing and varied timing instead of evenly spaced keys.[^twelve]

## Caveat

None of these tells proves anything on its own. Game assets are often fully triangulated, scans are dense, and blockouts are made of boxes. Game Developer's source makes the same point about photogrammetry.[^gamedev] Treat the checks as a list of things to improve, not as a verdict.

## Sources

[^neural4d]: Xinyi, ["Blender Retopology: How to Fix Bad Topology in AI 3D Models"](https://blog.neural4d.com/user-guide/blender-retopology-ai-3d-models/), Neural4D Blog. Used for: triangle soup and edge flow, non-manifold edges, holes, Meshy duplicate vertices, Tripo inverted normals and floating fragments, and the diagnosis steps in the [checklist](checklist.md).

[^gamedev]: Bryant Francis, ["How devs can spot AI-generated 3D models"](https://www.gamedeveloper.com/art/how-devs-can-spot-ai-generated-3d-models), Game Developer, November 5, 2024, with veteran 3D artist Liz Edwards. Used for: baked lighting, jumbled UVs, the crate polygon example, asymmetry and blobs, welded limbs, incoherent detail and the photogrammetry comparison.

[^sf3d]: Mark Boss et al. (Stability AI), ["SF3D: Stable Fast 3D Mesh Reconstruction with UV-unwrapping and Illumination Disentanglement"](https://arxiv.org/abs/2408.00653), 2024. Used for: Marching Cubes staircase artifacts and illumination baked into textures.

[^atomic]: Meghan Harris, ["What Happened When I Tried Blender Scripting with AI"](https://spin.atomicobject.com/blender-scripting-with-ai/), Atomic Object, July 7, 2025. Used for: Blender's stateful context, API version breakage and visual details needing manual work.

[^ll3m]: Threedle, [LL3M](https://github.com/threedle/ll3m): LLM agents that build 3D assets by writing Blender Python. Used as an example of script-built 3D.

[^leo]: Leo AI, [hands-on review of an AI assistant designing parts in Autodesk Fusion](https://www.getleo.ai/blog/claude-autodesk-fusion-3d-models-review), May 12, 2026. Used for: absolute coordinates instead of constrained sketches, brittle sketches, overlapping features, missing drafts and non-working snap fits.

[^threepoint]: Wikipedia, ["Three-point lighting"](https://en.wikipedia.org/wiki/Three-point_lighting). Used for: the roles of key, fill and back light, which the light-rig fix follows.

[^blendercm]: Blender Foundation, ["Color Management"](https://docs.blender.org/manual/en/4.2/render/color_management.html), Blender 4.2 Manual. Used for: what the *Standard* and *AgX* view transforms do.

[^twelve]: Wikipedia, ["Twelve basic principles of animation"](https://en.wikipedia.org/wiki/Twelve_basic_principles_of_animation), summarizing Ollie Johnston and Frank Thomas, *The Illusion of Life: Disney Animation* (1981). Used for: slow in and slow out, and timing.
