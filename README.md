````md
# CloudCompare LAS Class Subsampler

A CloudCompare PythonRuntime script for class-based LiDAR point cloud cleanup.

This script takes a classified LAS/LAZ point cloud loaded in CloudCompare, reduces point density for selected classes, keeps important feature classes at full density, optionally recolors selected classes, and creates a new merged cloud inside CloudCompare.

It was built for utility and powerline LiDAR workflows where ground and vegetation can be reduced, but powerlines, towers, buildings, and other important features should remain high quality.

---

## What It Does

Default behavior:

- Subsamples **Class 2 — Ground**
- Subsamples **Class 5 — High Vegetation**
- Keeps all other classes at full density
- Recolors:
  - **Class 16 — Powerline** to red
  - **Class 17 — Tower** to orange
- Preserves scalar fields where supported by CloudCompare PythonRuntime
- Creates a new merged cloud in the CloudCompare DB tree
- Does **not** modify the original point cloud

---

## Default Class Setup

The default script is configured around this classification scheme:

| Class ID | Description |
|---:|---|
| 1 | Unclassified |
| 2 | Ground |
| 3 | Low Vegetation |
| 5 | High Vegetation |
| 6 | Building |
| 9 | Water |
| 16 | Powerline |
| 17 | Tower |
| 29 | Bridge |

You can change the class IDs in the `CONFIG` block near the top of the script.

---

## Default Processing

```python
"subsample_classes": {
    2: 0.25,  # Ground
    5: 0.25,  # High vegetation
}
````

```python
"rgb_overrides": {
    16: (255, 0, 0),      # Powerline = red
    17: (255, 165, 0),    # Tower = orange
}
```

---

## Important Unit Warning

The subsampling spacing uses the point cloud’s coordinate units.

Examples:

| Cloud coordinate units |        `0.25` means |
| ---------------------- | ------------------: |
| Meters                 |         0.25 meters |
| Feet                   |           0.25 feet |
| US Survey Feet         | 0.25 US survey feet |

If your cloud is in StatePlane feet and you want approximately **0.25 meters**, use:

```python
0.82021
```

because:

```text
0.25 meters ≈ 0.82021 feet
```

---

## Requirements

* CloudCompare
* CloudCompare PythonRuntime plugin
* NumPy available inside the CloudCompare PythonRuntime environment

This script is intended to run **inside CloudCompare**, not from a normal terminal.

---

## Basic Usage

1. Open your classified LAS/LAZ file in CloudCompare.
2. Select the actual point cloud in the DB tree.

   * Select the cloud object itself, not just a parent group.
3. Open the PythonRuntime editor.
4. Paste or load the script.
5. Run it.
6. Wait for the new merged cloud to appear in the DB tree.
7. Review the output visually.
8. Save/export the final merged cloud if needed.

The final cloud name is controlled by:

```python
"final_cloud_name": "MERGED_class_subsampled_rgb"
```

---

## Recommended Workflow

For large point clouds, keep this setting:

```python
"add_class_clouds_to_db": False
```

This creates only the final merged cloud.

Do **not** set it to `True` unless you are working with a small test cloud. Creating per-class intermediate clouds can duplicate a large amount of data in memory and may crash CloudCompare.

---

## Dry Run Mode

To preview what the script will do without creating a new cloud, set:

```python
"dry_run_only": True
```

The script will print a class report showing:

* Classes found
* Point count per class
* Which classes will be subsampled
* Which classes will be recolored
* Which classes will remain full density

Example output:

```text
Class 2 (Ground): 18,923,551 points -> subsample spacing=0.25
Class 5 (High Vegetation): 32,551,883 points -> subsample spacing=0.25
Class 16 (Powerline): 45,992 points -> RGB override=(255, 0, 0)
Class 17 (Tower): 12,401 points -> RGB override=(255, 165, 0)
```

Set it back to `False` to run the actual processing.

---

## Configuration

All user-editable settings are located in the `CONFIG` block.

### Subsample Classes

```python
"subsample_classes": {
    2: 0.25,
    5: 0.25,
}
```

Format:

```python
class_id: spacing
```

Example:

```python
"subsample_classes": {
    2: 0.50,
    3: 0.25,
    5: 0.50,
}
```

This would subsample ground, low vegetation, and high vegetation.

---

### RGB Overrides

```python
"rgb_overrides": {
    16: (255, 0, 0),
    17: (255, 165, 0),
}
```

Format:

```python
class_id: (R, G, B)
```

RGB values are standard 8-bit values from `0` to `255`.

Examples:

```python
16: (255, 0, 0)      # Red
17: (255, 165, 0)    # Orange
29: (0, 170, 255)    # Blue
```

---

### Class Labels

Class labels are used for logging only.

```python
"class_labels": {
    1: "Unclassified",
    2: "Ground",
    3: "Low Vegetation",
    5: "High Vegetation",
    6: "Building",
    9: "Water",
    16: "Powerline",
    17: "Tower",
    29: "Bridge",
}
```

Changing these labels does not change the actual classification values. It only changes how the script reports them.

---

## Output

The script creates a new merged point cloud inside CloudCompare.

Default name:

```text
MERGED_class_subsampled_rgb
```

The original cloud remains unchanged.

---

## Memory Warning

Large LiDAR files can use a significant amount of RAM.

The script has a warning threshold:

```python
"max_warn_points": 50_000_000
```

If the source cloud is larger than this, the script prints a warning.

For large files:

```python
"add_class_clouds_to_db": False
```

should stay disabled.

---

## Point Order

The script preserves original point order by default:

```python
"preserve_original_order": True
```

This sorts the final point indices before creating the merged cloud.

Usually this is the safest behavior.

---

## How the Subsampling Works

The script uses a voxel/grid subsampling method.

For each class selected for subsampling:

1. It extracts all points from that class.
2. It divides space into grid cells based on the configured spacing.
3. It keeps one point per cell.
4. It adds the reduced class back into the final merged cloud.

Classes not listed in `subsample_classes` are kept at full density.

---

## Example Use Cases

### Utility / Powerline Dataset

Recommended:

```python
"subsample_classes": {
    2: 0.25,
    5: 0.25,
},
"rgb_overrides": {
    16: (255, 0, 0),
    17: (255, 165, 0),
}
```

This reduces ground and high vegetation while keeping powerlines and towers full density.

---

### Terrain-Focused Dataset

```python
"subsample_classes": {
    2: 0.50,
    3: 0.50,
    5: 0.50,
},
"rgb_overrides": {}
```

This reduces terrain and vegetation for a lighter surface/context cloud.

---

### Keep Buildings Full Density

Do not include class `6` in `subsample_classes`.

```python
"subsample_classes": {
    2: 0.25,
    5: 0.25,
}
```

Buildings will remain unchanged.

---

## Troubleshooting

### Script says no point cloud is selected

Make sure you selected the actual point cloud object in the DB tree, not just a parent group or file container.

Typical structure:

```text
classified.las
└── classified
```

Select the lower cloud object.

---

### CloudCompare crashes

Most likely cause:

```python
"add_class_clouds_to_db": True
```

Set it back to:

```python
"add_class_clouds_to_db": False
```

Large point clouds should only create the final merged cloud.

---

### Script is taking a long time

The slowest step is usually:

```text
Finding unique voxels...
```

This means the script is subsampling a large class.

To test faster, temporarily increase the spacing:

```python
"subsample_classes": {
    2: 1.0,
    5: 1.0,
}
```

Then lower it once the workflow is confirmed.

---

### Output does not look colored

Try displaying by scalar field or RGB in CloudCompare’s properties panel.

The script attempts to create RGB colors, but CloudCompare display/export behavior can vary by version.

---

## Limitations

* This script depends on CloudCompare PythonRuntime behavior, which may vary by CloudCompare version.
* It is designed for interactive CloudCompare use, not batch processing.
* Very large clouds may require significant RAM.
* The script creates a new in-memory CloudCompare cloud; it does not directly write LAS/LAZ from Python.
* CloudCompare export behavior can vary depending on file type, scalar field naming, and version.

For batch processing or production deliverables, a standalone `laspy` or `PDAL` version may be more reliable.

---

## Recommended Repository Structure

```text
cloudcompare-las-class-subsampler/
├── README.md
├── cloudcompare_class_subsample.py
├── LICENSE
└── examples/
    └── utility_config.md
```

---

## License

Recommended license:

```text
MIT License
```

This allows others to use, modify, and share the script freely.

---

## Disclaimer

Always verify the final cloud before delivery.

Recommended checks:

* Point count
* Classification field
* RGB/color display
* Coordinate system
* Global shift/scale
* Bounding box
* Critical classes such as powerlines, towers, buildings, and utilities

This script is provided as a practical utility and should be validated against your own data before production use.

```
```
