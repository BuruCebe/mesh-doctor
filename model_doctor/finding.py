"""Shared result type and the catalogue of checks."""

from dataclasses import dataclass

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"

# code -> (short title, category)
CODES = {
    "TRIANGLE_SOUP": ("Triangle soup", "Mesh"),
    "TRIANGULATED": ("Fully triangulated", "Mesh"),
    "HEAVY": ("Heavy mesh", "Mesh"),
    "LOOSE_BOXES": ("Stacked loose boxes", "Mesh"),
    "NON_MANIFOLD": ("Non-manifold edges", "Mesh"),
    "DUPLICATE_VERTS": ("Overlapping vertices", "Mesh"),
    "INVERTED_NORMALS": ("Inverted normals", "Mesh"),
    "NEGATIVE_SCALE": ("Mirrored by scale", "Mesh"),
    "NONUNIFORM_SCALE": ("Non-uniform scale", "Mesh"),
    "UNAPPLIED_SCALE": ("Unapplied scale", "Mesh"),
    "RAZOR_EDGES": ("Razor-sharp edges", "Mesh"),
    "FACETED": ("Faceted shading", "Mesh"),
    "BOX_SCENE": ("Scene of raw boxes", "Mesh"),
    "NO_UVS": ("No UV map", "UVs"),
    "FRAGMENTED_UVS": ("Shredded UVs", "UVs"),
    "NO_MATERIAL": ("No material", "Materials"),
    "FLAT_MATERIAL": ("Flat, uniform material", "Materials"),
    "BAKED_LIGHTING": ("Lighting baked into color", "Materials"),
    "COLOR_ONLY_TEXTURE": ("Color texture only", "Materials"),
    "MISSING_TEXTURE": ("Missing texture file", "Materials"),
    "FLAT_LIGHTING": ("Flat default lighting", "Lighting"),
    "SINGLE_LIGHT": ("Single light", "Lighting"),
    "STANDARD_VIEW": ("Harsh 'Standard' color view", "Lighting"),
    "DEFAULT_CAMERA": ("Default camera angle", "Camera"),
    "IDENTICAL_COPIES": ("Identical clones", "Scene"),
    "ODD_SCALE": ("Unrealistic scale", "Scene"),
    "UNORGANIZED": ("No collections", "Scene"),
    "MECHANICAL_TIMING": ("Robotic animation timing", "Animation"),
    "GENERIC_NAME": ("Generic name", "File"),
    "GENERATOR_NAME": ("Generator name", "File"),
    "LEFTOVER_SCRIPTS": ("Leftover scripts", "File"),
    "GENERIC_DATA_NAMES": ("Generic material names", "File"),
}
TITLES = {code: v[0] for code, v in CODES.items()}
CATEGORIES = ("Mesh", "UVs", "Materials", "Lighting", "Camera", "Scene", "Animation", "File")

OBJECT, MATERIAL, SCENE = "OBJECT", "MATERIAL", "SCENE"


@dataclass
class Finding:
    target: str        # name of the object / material, or "" for scene-level findings
    code: str
    severity: str
    message: str
    fix: str = ""      # key into fixes.FIXES, or "" if it needs a human
    kind: str = OBJECT  # what `target` names: OBJECT, MATERIAL or SCENE

    @property
    def category(self):
        return CODES[self.code][1]
