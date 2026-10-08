# Polish pass checklist

Run through this before you render, export or share a model. Items marked **(auto)** are checked by Mesh Doctor. The reasons behind each item, with sources, are in [The tells](tells.md).

## Blender

**Diagnose first.** Turn on *Overlays > Statistics*, run *Select > Select All by Trait > Non Manifold*, turn on *Overlays > Face Orientation*, and run the *3D Print Toolbox* checks. This order comes from Neural4D's retopology guide ([source](https://blog.neural4d.com/user-guide/blender-retopology-ai-3d-models/)). Then work through the list.

### Geometry
- [ ] **(auto)** No triangle soup. Imported scans and generator meshes get retopologized: *Remesh* (Quad), *QuadriFlow*, or manual retopo over the original.
- [ ] Density follows detail: flat areas have few faces, curves and details have more. **(auto)** flags very heavy meshes.
- [ ] **(auto)** No stacks of loose boxes standing in for detail. Use insets, extrudes, bevels and booleans.
- [ ] **(auto)** No non-manifold edges. *Select > Select All by Trait > Non Manifold*.
- [ ] **(auto)** Normals face outward. *Mesh > Normals > Recalculate Outside*, and check with *Overlays > Face Orientation*.
- [ ] **(auto)** No accidental overlapping vertices. *Mesh > Clean Up > Merge by Distance*.
- [ ] Parts that are separate in real life are separate objects; parts that are one piece are joined.

### Edges and shading
- [ ] **(auto)** Edges are broken. Add a *Bevel* modifier (Angle limit, 2–3 segments, Harden Normals) plus *Weighted Normal*.
- [ ] **(auto)** Curved surfaces are smooth shaded. *Object > Shade Auto Smooth* or *Shade Smooth by Angle*.
- [ ] No mushy corners where the object should be crisp.

### Transforms and data
- [ ] **(auto)** Scale is applied (*Ctrl+A > Scale*), especially before bevels, physics or export.
- [ ] **(auto)** No mirrored-by-scale objects; use a *Mirror* modifier instead.
- [ ] Origins are where the object pivots (hinge, base, center).
- [ ] Real-world size: a door is about 2 m tall.

### UVs, materials and names
- [ ] **(auto)** Everything that gets a texture is unwrapped, with seams in hidden places.
- [ ] Materials have some variation (roughness breakup, edge wear, dirt in crevices) instead of one flat color.
- [ ] No lighting baked into color textures.
- [ ] **(auto)** Objects and materials are named for what they are (`Hinge_Pin`, not `Cube.014` or `mesh_0`).
- [ ] **(auto)** Leftover scripts are removed from the file's text blocks before sharing.

### Final look
- [ ] Look at it from every side, including the bottom and back.
- [ ] Render a clay pass (one gray material). Bad shape and shading show up immediately.

## Fusion / CAD

- [ ] Parametric mode (timeline on), not direct modeling.
- [ ] **(auto)** Every sketch is fully constrained (black lines, not blue).
- [ ] **(auto)** Key sizes live in named user parameters.
- [ ] **(auto)** Edges are filleted or chamfered where a real part would be.
- [ ] Molded parts have draft; walls have consistent thickness.
- [ ] Features reference each other (project geometry, offset planes) instead of absolute coordinates.
- [ ] **(auto)** No mesh bodies left in the final design; rebuild them as solids.
- [ ] **(auto)** Bodies, components and sketches have real names.
- [ ] Changing one key parameter updates the model without errors in the timeline.
