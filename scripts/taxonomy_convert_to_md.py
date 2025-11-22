import json

def format_node_indented(node, indent_level=0):
    """
    Recursively formats a node into an indented list of strings.
    """
    
    # Indentation string
    indent = "  " * indent_level
    
    # Clean the name
    name = ' '.join(node['name'].split())
    
    # Start with the current node
    output_lines = [f"{indent}- {name}"]
    
    if 'children' in node and node['children']:
        # Recursively add children
        for child in node['children']:
            output_lines.extend(format_node_indented(child, indent_level + 1))
            
    return output_lines

def main():
    input_file = 'taxonomy.json'
    output_file = 'syllabus_indented.md' # .md or .txt
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        all_lines = []
        
        for paper in data['syllabus']:
            all_lines.extend(format_node_indented(paper, indent_level=0))
            all_lines.append("\n") # Add a space between papers
            
        # Join all lines with a newline
        final_output = "\n".join(all_lines)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_output)
            
        print(f"✅ Successfully converted to indented format in '{output_file}'")
        print(f"Total characters: {len(final_output)}")

    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()