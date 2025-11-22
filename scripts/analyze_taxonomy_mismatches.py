import json
import sys
import os
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load classified questions
with open('../tempnet/classified_questions.json', 'r') as f:
    questions = json.load(f)

# Load taxonomy
with open('taxonomy.json', 'r') as f:
    taxonomy_data = json.load(f)

# Build all valid paths from taxonomy
def flatten_taxonomy(node, parent_path="", paths=None):
    if paths is None:
        paths = []
    
    current_name = node.get("name", "")
    if parent_path:
        full_path = f"{parent_path} > {current_name}"
    else:
        full_path = current_name
        
    paths.append(full_path)
    
    for child in node.get("children", []):
        flatten_taxonomy(child, full_path, paths)
        
    return paths

valid_paths = set()
for item in taxonomy_data.get("syllabus", []):
    for path in flatten_taxonomy(item):
        valid_paths.add(path)

print(f"Total valid taxonomy paths: {len(valid_paths)}")

# Collect all paths from classified questions
classifier_paths = set()
path_frequency = defaultdict(int)

for q in questions:
    for path in q.get("taxonomy_paths", []):
        classifier_paths.add(path)
        path_frequency[path] += 1

print(f"Total unique classifier paths: {len(classifier_paths)}")

# Find mismatches
missing_paths = classifier_paths - valid_paths
print(f"\nMissing paths (in classifier but not in taxonomy): {len(missing_paths)}")

# Sort by frequency
missing_sorted = sorted(missing_paths, key=lambda p: path_frequency[p], reverse=True)

print("\nTop 20 missing paths by frequency:")
for i, path in enumerate(missing_sorted[:20], 1):
    print(f"{i}. [{path_frequency[path]}x] {path}")

# Save all missing paths
with open('missing_taxonomy_paths.json', 'w') as f:
    json.dump({
        "missing_paths": [{"path": p, "count": path_frequency[p]} for p in missing_sorted],
        "total_missing": len(missing_paths)
    }, f, indent=2)

print(f"\nSaved all missing paths to missing_taxonomy_paths.json")

# Try to find similar paths
print("\n\nAnalyzing mismatches...")
for missing_path in missing_sorted[:10]:
    parts = missing_path.split(" > ")
    print(f"\nMissing: {missing_path}")
    
    # Find paths with similar structure
    similar = []
    for valid_path in valid_paths:
        valid_parts = valid_path.split(" > ")
        if len(valid_parts) == len(parts):
            # Check if any part matches
            matches = sum(1 for i in range(len(parts)) if parts[i] == valid_parts[i])
            if matches > 0:
                similar.append((matches, valid_path))
    
    if similar:
        similar.sort(reverse=True)
        print(f"  Similar paths (top 3):")
        for match_count, sim_path in similar[:3]:
            print(f"    [{match_count}/{len(parts)} parts match] {sim_path}")
