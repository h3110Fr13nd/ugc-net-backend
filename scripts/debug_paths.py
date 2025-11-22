import json

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

# Get sample paths from questions
sample_paths = set()
for q in questions[:100]:
    for path in q.get("taxonomy_paths", []):
        sample_paths.add(path)

print("Sample paths from questions:")
for p in list(sample_paths)[:5]:
    print(f"  '{p}'")

print("\nSample valid paths from taxonomy:")
for p in list(valid_paths)[:5]:
    print(f"  '{p}'")

# Check the specific missing path
missing = "General Paper on Teaching & Research Aptitude (Paper I) > Unit-III: Comprehension > A passage of text be given. Questions be asked from the passage to be answered"
print(f"\nMissing path in valid_paths? {missing in valid_paths}")

# Find similar
for vp in valid_paths:
    if "Comprehension" in vp and "passage" in vp.lower():
        print(f"  Similar: '{vp}'")
