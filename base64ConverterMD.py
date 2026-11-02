import base64
import re
import os

def image_to_base64(image_path):
    ext = os.path.splitext(image_path)[1][1:].lower()  # Get file extension without the dot
    if not os.path.exists(image_path):
        print(f"⚠️ File not found: {image_path}")
        return None
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return f"data:image/{ext};base64,{encoded_string}"

def convert_md_images_to_base64(md_path):
    base_dir = os.path.dirname(md_path)
    
    with open(md_path, "r", encoding="utf-8") as file:
        content = file.read()

    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

    def replacer(match):
        alt_text = match.group(1)
        image_rel_path = match.group(2).strip()
        image_abs_path = os.path.join(base_dir, image_rel_path)

        base64_data = image_to_base64(image_abs_path)
        if base64_data:
            return f"![{alt_text}]({base64_data})"
        else:
            return match.group(0)  # leave it unchanged if failed

    updated_content = re.sub(pattern, replacer, content)

    output_path = md_path.replace(".md", "_base64.md")
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(updated_content)

    print(f"✅ Converted and saved: {output_path}")

# Example usage
if __name__ == "__main__":
    convert_md_images_to_base64("MarkdownFiles/ikea_skadis_addons.md")  # path to your MD file
