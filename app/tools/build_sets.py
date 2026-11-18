"""Build the five show sets in client/story/sets/ from Kenney's CC0 kits.

    .venv/bin/python app/tools/build_sets.py <folder with the unzipped kits>

Positions are of the model's footprint centre, in metres. The cast stands in
x -2.8..2.8, z -1.5..2.0, facing +z.
"""

import json
import os
import shutil
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(APP_DIR, "client", "story", "sets")
KITS = {
    "nature": ("nature-kit", "Models/GLTF format", "Nature Kit"),
    "furniture": ("furniture-kit", "Models/GLTF format", "Furniture Kit"),
    "pirate": ("pirate-kit", "Models/GLB format", "Pirate Kit"),
    "space": ("space-kit", "Models/GLTF format", "Space Kit"),
}
ACTION_AREA = (3.2, -1.5)  # |x| below this and z above this is the cast's
FLAT = 0.05  # metres; a rug may lie in the action area


def P(kit, model, x, z, scale, rot=0, y=0.0):
    return {
        "kit": kit,
        "model": model,
        "position": [x, y, z],
        "rotationY": rot,
        "scale": scale,
    }


def park():
    n, s = "nature", 2.6
    return [
        P(n, "tree_default", -5.5, -4.5, s),
        P(n, "tree_oak", 5.0, -5.0, s, 40),
        P(n, "tree_fat", -2.2, -7.5, s, 15),
        P(n, "tree_detailed", 2.6, -8.0, s),
        P(n, "tree_default", 8.2, -2.8, s, 70),
        P(n, "tree_oak", -8.6, -2.0, s),
        P(n, "tree_fat", 7.0, 1.0, s, 120),
        P(n, "tree_detailed", -6.8, 1.2, s, 200),
        P(n, "tree_default", -11.0, -7.0, s),
        P(n, "tree_oak", 11.0, -7.5, s),
        P(n, "plant_bushLarge", -3.7, -2.6, s),
        P(n, "plant_bush", 3.9, -2.4, s),
        P(n, "plant_bushLarge", 0.8, -4.4, s, 30),
        P(n, "plant_bush", -1.4, -4.6, s),
        P(n, "plant_bushLarge", 5.4, -0.2, s),
        P(n, "plant_bush", -5.2, -1.2, s),
        P(n, "flower_redA", -3.5, -1.0, s),
        P(n, "flower_yellowA", 3.6, -0.6, s),
        P(n, "flower_purpleA", 4.3, 1.3, s),
        P(n, "flower_redA", -4.4, 1.7, s, 90),
        P(n, "flower_yellowA", -0.4, -3.0, s),
        P(n, "flower_purpleA", 2.0, -3.3, s),
        P(n, "flower_redA", 1.0, -2.4, s, 45),
        P(n, "flower_yellowA", -2.4, -2.2, s, 60),
        P(n, "rock_largeA", 5.8, -2.2, s, 25),
        P(n, "stump_round", -4.8, -0.2, s),
        P(n, "mushroom_redGroup", -3.6, 0.7, s),
        P(n, "log", 4.9, 3.0, s, 70),
    ]


def room():
    f, s = "furniture", 2.3
    back, side = -3.3, 8.05
    walls = [
        P(f, "wallWindow" if x in (-4.6, 4.6) else "wall", x, back, s)
        for x in (-6.9, -4.6, -2.3, 0.0, 2.3, 4.6, 6.9)
    ]
    walls += [
        P(f, "wall", sign * side, z, s, 90 * sign)
        for sign in (-1, 1)
        for z in (-2.15, 0.15, 2.45)
    ]
    return walls + [
        P(f, "rugRound", 0.0, 0.3, 2.9),
        P(f, "loungeSofa", -4.4, -2.75, s),
        P(f, "tableCoffee", -4.4, -1.1, s),
        P(f, "lampRoundFloor", -6.6, -2.8, s),
        P(f, "bear", -6.4, -1.0, s, 35),
        P(f, "cabinetTelevision", 1.6, -3.0, s),
        P(f, "televisionVintage", 1.6, -3.0, s, 0, 0.72),
        P(f, "bookcaseOpen", 4.3, -3.0, s),
        P(f, "bookcaseOpen", 5.3, -3.0, s),
        P(f, "pottedPlant", 6.8, -2.7, s),
        P(f, "cardboardBoxOpen", 5.6, -0.6, s, -20),
        P(f, "pottedPlant", -2.0, -3.0, 2.0),
    ]


def beach():
    p = "pirate"
    return [
        P(p, "palm-straight", -5.2, -3.6, 1.0),
        P(p, "palm-bend", 5.0, -2.6, 1.0, -30),
        P(p, "palm-straight", 7.8, -6.0, 1.1, 50),
        P(p, "palm-bend", -8.4, -1.0, 1.0, 160),
        P(p, "palm-detailed-straight", -10.5, -6.5, 1.1),
        P(p, "palm-detailed-bend", 10.5, -1.5, 1.0, -80),
        P(p, "chest", 3.9, -0.7, 0.6, -30),
        P(p, "barrel", -3.9, -1.2, 0.55),
        P(p, "barrel", -4.7, -0.3, 0.5, 40),
        P(p, "crate", -4.5, -2.2, 0.55, 15),
        P(p, "rocks-sand-a", 7.0, -5.5, 0.6),
        P(p, "rocks-sand-b", -7.0, -6.0, 0.5, 60),
        P(p, "flag-pirate", 4.6, -3.8, 0.9, 20),
        P(p, "patch-sand-foliage", -6.0, 2.5, 0.5),
        P(p, "ship-pirate-large", -17.0, -48.0, 1.0, 70),
        P(p, "boat-row-small", 6.5, -9.5, 0.7, 30),
    ]


def space():
    x, s = "space", 2.5
    rocket = [
        P(x, part, 6.4, -6.5, s, 0, y * s)
        for part, y in (
            ("rocket_baseA", 0.0),
            ("rocket_fuelA", 1.6),
            ("rocket_sidesA", 2.1),
            ("rocket_topA", 3.1),
        )
    ]
    return rocket + [
        P(x, "hangar_roundGlass", -6.8, -7.5, s),
        P(x, "satelliteDish_large", -4.3, -2.9, 2.2, 30),
        P(x, "rover", 4.2, -1.1, s, -40),
        P(x, "crater", -3.9, 1.3, 3.0),
        P(x, "craterLarge", 2.4, -4.0, 3.0),
        P(x, "rock_crystalsLargeA", 4.7, 1.6, 2.0, 60),
        P(x, "rock_largeA", -5.6, 0.4, 2.0),
        P(x, "meteor_detailed", 1.4, -7.5, 2.5, 20),
        P(x, "rock_crystalsLargeA", -1.6, -5.6, 2.2),
        P(x, "craterLarge", -8.0, -3.0, 3.5),
        P(x, "rock_largeA", 8.6, 0.5, 2.5, 90),
    ]


SETS = [
    {
        "id": "stage",
        "name": "Stage",
        "description": "An empty white stage, like Pocoyo: nothing but the characters.",
        "light": "studio",
        "ground": {"color": "#f4f4ef", "size": 80, "shadowOnly": True},
        "props": [],
    },
    {
        "id": "park",
        "name": "Park",
        "description": "A sunny park with trees, bushes and flowers.",
        "light": "day",
        "ground": {"color": "#8cc96b", "size": 80},
        "props": park(),
    },
    {
        "id": "room",
        "name": "Room",
        "description": "A cosy kid's room with a sofa, a rug, shelves and toys.",
        "light": "day",
        "ground": {"color": "#d9b48a", "size": 17},
        "background": "#efe3d0",
        "props": room(),
    },
    {
        "id": "beach",
        "name": "Beach",
        "description": "A sandy beach with palm trees, a treasure chest and a pirate ship at sea.",
        "light": "day",
        "ground": {"color": "#f2dca4", "size": 80},
        "water": {"color": "#3fa7d6", "z": -8.0},
        "props": beach(),
    },
    {
        "id": "space",
        "name": "Moon",
        "description": "The surface of the moon, with rocks, a rocket and stars.",
        "light": "night",
        "ground": {"color": "#a7a7b0", "size": 80},
        "background": "#05060f",
        "stars": True,
        "planet": {"color": "#3f7fe0", "position": [-16, 11, -40], "radius": 3.2},
        "props": space(),
    },
]


def build(kits_dir):
    used = {}
    for s in SETS:
        folder = os.path.join(OUT, s["id"])
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        os.makedirs(os.path.join(folder, "models"))
        props = []
        for prop in s["props"]:
            kit, sub, _ = KITS[prop["kit"]]
            source = os.path.join(kits_dir, kit, "x", sub, prop["model"] + ".glb")
            if not os.path.exists(source):
                source = os.path.join(kits_dir, kit, sub, prop["model"] + ".glb")
            name = f"{prop['kit']}-{prop['model']}.glb"
            shutil.copyfile(source, os.path.join(folder, "models", name))
            textures = os.path.join(os.path.dirname(source), "Textures")
            if os.path.isdir(textures):  # the Pirate Kit's GLBs read Textures/colormap.png
                shutil.copytree(textures, os.path.join(folder, "models", "Textures"), dirs_exist_ok=True)
            used.setdefault(prop["kit"], set()).add(prop["model"])
            props.append(
                {
                    "model": f"models/{name}",
                    "position": prop["position"],
                    "rotationY": prop["rotationY"],
                    "scale": prop["scale"],
                }
            )
        data = {k: v for k, v in s.items() if k != "props"}
        data["props"] = props
        with open(os.path.join(folder, "set.json"), "w") as f:
            json.dump(data, f, indent=1)
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump(
            [
                {"id": s["id"], "name": s["name"], "description": s["description"]}
                for s in SETS
            ],
            f,
            indent=1,
        )
    lines = [
        "# Credits for the show sets",
        "",
        "Every model in these folders is by **Kenney** (https://www.kenney.nl), released under "
        "**Creative Commons Zero (CC0)**: http://creativecommons.org/publicdomain/zero/1.0/ ."
        " Kenney asks for credit but does not require it; we give it anyway.",
        "",
    ]
    for key, (kit, _, title) in KITS.items():
        if key in used:
            lines.append(
                f"- {title} (https://kenney.nl/assets/{kit}): {', '.join(sorted(used[key]))}"
            )
    lines += [
        "",
        "The characters in client/story/characters/ are from **100Avatars** by Polygonal Mind, also CC0.",
        "",
        "Rebuild with `.venv/bin/python app/tools/build_sets.py <folder with the unzipped kits>`.",
        "",
    ]
    with open(os.path.join(OUT, "CREDITS.md"), "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
    total = sum(
        os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(OUT) for f in fs
    )
    print(f"sets written to {OUT}: {total // 1024} KB")
