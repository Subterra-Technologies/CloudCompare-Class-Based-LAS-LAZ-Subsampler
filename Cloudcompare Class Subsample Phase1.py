"""
CloudCompare Class-Based LAS/LAZ Subsampler
============================================

Purpose
-------
This script is intended to be run inside CloudCompare's Python Runtime plugin.
It takes the currently selected point cloud, reads its Classification scalar field,
subsamples configured classes, optionally recolors configured classes, and creates
one final merged cloud inside CloudCompare.

Default behavior
----------------
- Subsamples class 2 (Ground) to 0.25 coordinate units
- Subsamples class 5 (High Vegetation) to 0.25 coordinate units
- Recolors class 16 (Powerline) red
- Recolors class 17 (Tower) orange
- Keeps all other classes at full density
- Creates only one final merged cloud by default

Important unit warning
----------------------
The spacing values use the coordinate units of the point cloud.

Examples:
- If the cloud is in meters: 0.25 = 0.25 meters
- If the cloud is in US survey feet/international feet: 0.25 = 0.25 feet
- 0.25 meters is approximately 0.82021 feet

Large file warning
------------------
Keep ADD_CLASS_CLOUDS_TO_DB = False for large point clouds. Creating per-class
intermediate clouds duplicates point data in memory and can crash CloudCompare.

Saving
------
This script does not automatically save to disk. It creates a new cloud in the
CloudCompare DB tree. After running:

1. Select the final merged cloud.
2. File -> Save.
3. Choose LAS or LAZ.
4. Reopen the saved file to verify Classification and RGB.
"""

import time

import numpy as np
import pycc


# ============================================================
# CONFIGURATION
# ============================================================

CONFIG = {
    # Subsample these classes using voxel/grid spacing.
    # Format: class_id: spacing
    # Spacing uses the point cloud's coordinate units.
    "subsample_classes": {
        2: 0.25,  # Ground
        5: 0.25,  # High vegetation
    },

    # Force RGB colors for these classes in the final cloud.
    # Format: class_id: (R, G, B), values 0-255.
    "rgb_overrides": {
        16: (255, 0, 0),      # Powerline = red
        17: (255, 165, 0),    # Tower = orange
    },

    # Optional class labels used only for logging/reporting.
    "class_labels": {
        1: "Unclassified",
        2: "Ground",
        3: "Low Vegetation",
        4: "Medium Vegetation",
        5: "High Vegetation",
        6: "Building",
        9: "Water",
        16: "Powerline",
        17: "Tower",
        29: "Bridge",
    },

    # Output cloud name inside the CloudCompare DB tree.
    "final_cloud_name": "MERGED_class_subsampled_rgb",

    # Run report only. No final cloud is created when True.
    "dry_run_only": False,

    # Keep False for large clouds. True duplicates data and can crash CloudCompare.
    "add_class_clouds_to_db": False,

    # Preserve original point order in final output by sorting final indices.
    # Recommended True.
    "preserve_original_order": True,

    # Warn if the source cloud is larger than this many points.
    "max_warn_points": 50_000_000,

    # If source RGB is missing, assign basic class fallback colors.
    "use_fallback_colors_when_no_rgb": True,
}


# ============================================================
# LOGGING
# ============================================================

SCRIPT_START = time.time()


def log(message):
    elapsed = time.time() - SCRIPT_START
    print(f"[{elapsed:8.1f}s] {message}", flush=True)


def class_label(class_id):
    label = CONFIG["class_labels"].get(int(class_id))
    if label:
        return f"{class_id} ({label})"
    return str(class_id)


# ============================================================
# CLOUDCOMPARE ENTITY HELPERS
# ============================================================


def is_point_cloud(entity):
    return hasattr(entity, "points") and hasattr(entity, "size")


def get_children(entity):
    children = []
    if hasattr(entity, "getChildrenNumber") and hasattr(entity, "getChild"):
        try:
            for i in range(entity.getChildrenNumber()):
                children.append(entity.getChild(i))
        except Exception:
            pass
    return children


def find_cloud_recursive(entity):
    if is_point_cloud(entity):
        return entity

    for child in get_children(entity):
        found = find_cloud_recursive(child)
        if found is not None:
            return found

    return None


def find_cloud_from_selection_or_db():
    cc = pycc.GetInstance()

    log("Checking selected entities...")
    selected = cc.getSelectedEntities()

    if selected:
        log(f"Selected entity count: {len(selected)}")
        for entity in selected:
            try:
                log(f"Selected entity: {entity.getName()} | {type(entity)}")
            except Exception:
                log(f"Selected entity type: {type(entity)}")

            found = find_cloud_recursive(entity)
            if found is not None:
                log(f"Using selected cloud: {found.getName()}")
                return found

    log("No usable selected cloud found. Searching DB tree...")

    possible_roots = []
    for method_name in ["getRootEntity", "dbRootObject", "getDBRoot"]:
        if hasattr(cc, method_name):
            try:
                root = getattr(cc, method_name)()
                if root is not None:
                    possible_roots.append(root)
                    log(f"Found possible DB root via: {method_name}")
            except Exception:
                pass

    for root in possible_roots:
        found = find_cloud_recursive(root)
        if found is not None:
            log(f"Using cloud found in DB: {found.getName()}")
            return found

    raise RuntimeError(
        "Could not find a point cloud. Select the actual point cloud in the DB tree."
    )


# ============================================================
# SCALAR FIELD HELPERS
# ============================================================


def get_scalar_field_count(cloud):
    return cloud.getNumberOfScalarFields()


def get_scalar_field_name(cloud, index):
    try:
        return cloud.getScalarFieldName(index)
    except Exception:
        scalar_field = cloud.getScalarField(index)
        if hasattr(scalar_field, "getName"):
            return scalar_field.getName()
        return f"ScalarField_{index}"


def find_classification_sf_index(cloud):
    preferred_names = [
        "Classification",
        "classification",
        "Class",
        "class",
        "LAS classification",
    ]

    if hasattr(cloud, "getScalarFieldIndexByName"):
        for name in preferred_names:
            try:
                idx = cloud.getScalarFieldIndexByName(name)
                if idx != -1:
                    log(f"Found classification scalar field by name: {name}")
                    return idx
            except Exception:
                pass

    sf_count = get_scalar_field_count(cloud)
    log("Scalar fields found:")
    for i in range(sf_count):
        name = get_scalar_field_name(cloud, i)
        log(f"  {i}: {name}")
        if "class" in name.lower():
            log(f"Using scalar field as classification: {name}")
            return i

    raise RuntimeError(
        "Could not find a Classification scalar field. Make sure LAS classifications "
        "were imported as scalar fields."
    )


def get_points_array(cloud):
    log("Reading point coordinates into NumPy array...")
    start = time.time()
    points = np.asarray(cloud.points())
    log(f"Loaded coordinates array: shape={points.shape}, time={time.time() - start:.1f}s")

    if points.ndim != 2 or points.shape[1] != 3:
        raise RuntimeError("Point array is not Nx3.")

    return points


def get_scalar_array(cloud, sf_index):
    log("Reading Classification scalar field into NumPy array...")
    start = time.time()
    scalar_field = cloud.getScalarField(sf_index)
    array = np.asarray(scalar_field.asArray())
    log(f"Loaded scalar array: length={len(array):,}, time={time.time() - start:.1f}s")
    return array


# ============================================================
# GLOBAL SHIFT / SCALE
# ============================================================


def copy_global_shift_and_scale(src_cloud, dst_cloud):
    try:
        shift = src_cloud.getGlobalShift()
        try:
            dst_cloud.setGlobalShift(shift)
        except Exception:
            dst_cloud.setGlobalShift(shift.x, shift.y, shift.z)
        log("Copied global shift.")
    except Exception:
        log("Warning: could not copy global shift.")

    try:
        scale = src_cloud.getGlobalScale()
        dst_cloud.setGlobalScale(scale)
        log("Copied global scale.")
    except Exception:
        pass


# ============================================================
# REPORTING
# ============================================================


def print_processing_report(classification):
    unique_classes, counts = np.unique(classification, return_counts=True)

    log("============================================")
    log("CLASS REPORT")
    log("============================================")

    subsample_classes = CONFIG["subsample_classes"]
    rgb_overrides = CONFIG["rgb_overrides"]

    for class_id, count in zip(unique_classes, counts):
        class_id = int(class_id)
        actions = []

        if class_id in subsample_classes:
            actions.append(f"subsample spacing={subsample_classes[class_id]}")

        if class_id in rgb_overrides:
            actions.append(f"RGB override={rgb_overrides[class_id]}")

        if not actions:
            actions.append("keep full density")

        log(f"Class {class_label(class_id)}: {int(count):,} points -> {', '.join(actions)}")


# ============================================================
# RGB COLOR HELPERS
# ============================================================


def get_existing_rgb_color(src_cloud, src_i):
    color = src_cloud.getPointColor(int(src_i))

    try:
        r = int(color.r)
        g = int(color.g)
        b = int(color.b)
    except Exception:
        r = int(color[0])
        g = int(color[1])
        b = int(color[2])

    # If values look like 16-bit LAS RGB, scale to 8-bit.
    if r > 255 or g > 255 or b > 255:
        r = int(round(r / 257.0))
        g = int(round(g / 257.0))
        b = int(round(b / 257.0))

    return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))


def fallback_color_for_class(class_id):
    if class_id == 1:
        return (180, 180, 180)  # Unclassified gray
    if class_id == 2:
        return (120, 90, 60)    # Ground brown
    if class_id == 3:
        return (80, 180, 80)    # Low vegetation green
    if class_id == 4:
        return (50, 150, 50)    # Medium vegetation green
    if class_id == 5:
        return (30, 120, 30)    # High vegetation dark green
    if class_id == 6:
        return (200, 200, 200)  # Building light gray
    if class_id == 9:
        return (0, 120, 255)    # Water blue
    return (180, 180, 180)


def copy_rgb_colors(src_cloud, dst_cloud, indices):
    log("  Preparing RGB colors...")

    class_idx = find_classification_sf_index(src_cloud)
    class_arr = np.asarray(src_cloud.getScalarField(class_idx).asArray()).astype(np.int32)

    try:
        source_has_colors = src_cloud.hasColors()
    except Exception:
        source_has_colors = False

    log(f"  Source has RGB colors: {source_has_colors}")

    total = len(indices)
    rgb = np.zeros((total, 3), dtype=np.uint8)
    progress_step = max(total // 10, 1)

    log(f"  Building RGB array for {total:,} points...")

    for out_i, src_i in enumerate(indices):
        src_i = int(src_i)
        class_id = int(class_arr[src_i])

        if class_id in CONFIG["rgb_overrides"]:
            rgb[out_i, :] = CONFIG["rgb_overrides"][class_id]
        elif source_has_colors:
            try:
                rgb[out_i, :] = get_existing_rgb_color(src_cloud, src_i)
            except Exception:
                rgb[out_i, :] = fallback_color_for_class(class_id)
        elif CONFIG["use_fallback_colors_when_no_rgb"]:
            rgb[out_i, :] = fallback_color_for_class(class_id)
        else:
            rgb[out_i, :] = (180, 180, 180)

        if out_i > 0 and out_i % progress_step == 0:
            log(f"    RGB build progress: {100.0 * out_i / total:.0f}%")

    try:
        log("  Assigning RGB array with dst_cloud.setColors(rgb)...")
        dst_cloud.setColors(rgb)
        dst_cloud.showColors(True)
        dst_cloud.showSF(False)
        log("  RGB colors assigned successfully using setColors().")
        return
    except Exception as error:
        log(f"  setColors() failed: {error}")

    log("  Falling back to resizeTheRGBTable() + setPointColor().")

    try:
        dst_cloud.resizeTheRGBTable()
        has_pycc_rgb = hasattr(pycc, "Rgb")

        for i in range(total):
            r = int(rgb[i, 0])
            g = int(rgb[i, 1])
            b = int(rgb[i, 2])

            if has_pycc_rgb:
                dst_cloud.setPointColor(i, pycc.Rgb(r, g, b))
            else:
                dst_cloud.setPointColor(i, (r, g, b))

            if i > 0 and i % progress_step == 0:
                log(f"    RGB fallback write progress: {100.0 * i / total:.0f}%")

        dst_cloud.showColors(True)
        dst_cloud.showSF(False)
        log("  RGB colors assigned using fallback setPointColor().")
    except Exception as error:
        log(f"  RGB fallback failed: {error}")
        log("  Cloud is still valid, but RGB may not display.")


# ============================================================
# SUBSAMPLING
# ============================================================


def voxel_subsample_indices(points, spacing):
    if len(points) == 0:
        return np.array([], dtype=np.int64)

    log(f"  Voxel subsample started on {len(points):,} points at spacing={spacing}")
    start = time.time()

    log("  Computing voxel coordinates...")
    minimums = points.min(axis=0)
    voxel_indices = np.floor((points - minimums) / spacing).astype(np.int64)

    log("  Building voxel keys...")
    keys = np.empty(
        len(voxel_indices),
        dtype=[("x", np.int64), ("y", np.int64), ("z", np.int64)],
    )
    keys["x"] = voxel_indices[:, 0]
    keys["y"] = voxel_indices[:, 1]
    keys["z"] = voxel_indices[:, 2]

    log("  Finding unique voxels. This may take a while...")
    _, keep = np.unique(keys, return_index=True)
    keep = np.sort(keep)

    log(
        f"  Voxel subsample complete: {len(points):,} -> {len(keep):,} "
        f"in {time.time() - start:.1f}s"
    )

    return keep


# ============================================================
# CLOUD CREATION
# ============================================================


def create_cloud_from_indices(src_cloud, indices, name):
    log(f"Creating new cloud: {name}")
    log(f"  Point count: {len(indices):,}")
    start = time.time()

    src_points = np.asarray(src_cloud.points())
    subset_points = src_points[indices]

    log("  Creating ccPointCloud object...")
    new_cloud = pycc.ccPointCloud(
        subset_points[:, 0],
        subset_points[:, 1],
        subset_points[:, 2],
    )
    new_cloud.setName(name)
    copy_global_shift_and_scale(src_cloud, new_cloud)

    copy_rgb_colors(src_cloud, new_cloud, indices)

    sf_count = get_scalar_field_count(src_cloud)
    log(f"  Copying {sf_count} scalar fields...")

    for sf_i in range(sf_count):
        sf_name = get_scalar_field_name(src_cloud, sf_i)
        log(f"    Copying scalar field {sf_i + 1}/{sf_count}: {sf_name}")

        src_sf_arr = np.asarray(src_cloud.getScalarField(sf_i).asArray())
        new_sf_idx = new_cloud.addScalarField(sf_name)
        new_sf_arr = new_cloud.getScalarField(new_sf_idx).asArray()
        new_sf_arr[:] = src_sf_arr[indices]

        try:
            new_cloud.getScalarField(new_sf_idx).computeMinAndMax()
        except Exception:
            pass

    try:
        if hasattr(new_cloud, "hasColors") and new_cloud.hasColors():
            new_cloud.showColors(True)
            new_cloud.showSF(False)
            log("  Display set to RGB colors.")
        else:
            class_idx = find_classification_sf_index(new_cloud)
            new_cloud.setCurrentDisplayedScalarField(class_idx)
            new_cloud.showSF(True)
            log("  Display set to Classification scalar field.")
    except Exception as error:
        log(f"  Display setup warning: {error}")

    log(f"Finished creating cloud '{name}' in {time.time() - start:.1f}s")
    return new_cloud


# ============================================================
# MAIN
# ============================================================


def main():
    cc = pycc.GetInstance()

    log("Script started.")
    cloud = find_cloud_from_selection_or_db()

    log("============================================")
    log("SOURCE CLOUD")
    log("============================================")
    log(f"Name: {cloud.getName()}")
    log(f"Point count: {cloud.size():,}")

    if cloud.size() >= CONFIG["max_warn_points"]:
        log("WARNING: Very large point cloud detected.")
        log("Keep add_class_clouds_to_db=False unless you have substantial RAM.")

    try:
        log(f"Source cloud has RGB colors: {cloud.hasColors()}")
    except Exception:
        log("Could not determine whether source cloud has RGB colors.")

    classification_sf_idx = find_classification_sf_index(cloud)
    points = get_points_array(cloud)
    classification = get_scalar_array(cloud, classification_sf_idx).astype(np.int32)

    if len(classification) != cloud.size():
        raise RuntimeError("Classification scalar field length does not match point count.")

    print_processing_report(classification)

    if CONFIG["dry_run_only"]:
        log("DRY_RUN_ONLY=True. Stopping after report. No cloud was created.")
        return

    final_index_chunks = []

    log("============================================")
    log("PROCESSING CLASSES")
    log("============================================")

    unique_classes = np.unique(classification)

    for class_id in unique_classes:
        class_id = int(class_id)
        log("--------------------------------------------")
        log(f"Processing class {class_label(class_id)}")
        start_class = time.time()

        log("  Finding points for this class...")
        class_indices = np.where(classification == class_id)[0]
        log(f"  Original points: {len(class_indices):,}")

        if class_id in CONFIG["subsample_classes"]:
            spacing = CONFIG["subsample_classes"][class_id]
            log(f"  Class {class_label(class_id)} is marked for subsampling.")
            log("  Extracting class point coordinates...")
            class_points = points[class_indices]
            keep_local_indices = voxel_subsample_indices(class_points, spacing)
            final_indices = class_indices[keep_local_indices]
            log(f"  Final points for class {class_label(class_id)}: {len(final_indices):,}")
        else:
            final_indices = class_indices
            log("  Class kept full density.")

        final_index_chunks.append(final_indices)

        if CONFIG["add_class_clouds_to_db"]:
            suffix = "subsampled" if class_id in CONFIG["subsample_classes"] else "full_density"
            class_cloud_name = f"class_{class_id}_{suffix}"
            class_cloud = create_cloud_from_indices(cloud, final_indices, class_cloud_name)
            cc.addToDB(class_cloud)
            log(f"  Added class cloud to DB: {class_cloud_name}")

        log(f"Finished class {class_label(class_id)} in {time.time() - start_class:.1f}s")

    log("============================================")
    log("MERGING FINAL INDEX LIST")
    log("============================================")

    start_merge = time.time()
    final_indices_all = np.concatenate(final_index_chunks).astype(np.int64)

    if CONFIG["preserve_original_order"]:
        log("Sorting final indices to preserve original point order...")
        final_indices_all = np.sort(final_indices_all)

    log(f"Final merged index count: {len(final_indices_all):,}")
    log(f"Index merge time: {time.time() - start_merge:.1f}s")

    log("============================================")
    log("CREATING FINAL CLOUD")
    log("============================================")

    merged_cloud = create_cloud_from_indices(
        cloud,
        final_indices_all,
        CONFIG["final_cloud_name"],
    )

    log("Adding final merged cloud to CloudCompare DB...")
    cc.addToDB(merged_cloud)

    try:
        cc.updateUI()
    except Exception:
        pass

    log("============================================")
    log("DONE")
    log("============================================")
    log(f"Final cloud name: {CONFIG['final_cloud_name']}")
    log(f"Final point count: {merged_cloud.size():,}")
    log("")
    log("Next:")
    log("1. Select the final merged cloud in the DB tree.")
    log("2. Verify RGB display and Classification scalar field.")
    log("3. File -> Save.")
    log("4. Choose LAS or LAZ.")
    log("5. Reopen the saved file to verify RGB and Classification.")


main()
