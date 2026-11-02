import os
import re
import base64

def extract_and_save_images(md_content, md_path):
    """
    Finds base64 images in the markdown content, saves them as image files,
    and replaces the image src with a file path relative to the markdown file.
    """
    image_dir = os.path.dirname(md_path)
    img_tag_pattern = r'!\[(.*?)\]\((data:image/[^;]+;base64,.*?)\)'

    def replace_func(match):
        alt_text, base64_data = match.groups()
        file_type = re.search(r'data:image/(\w+);base64', base64_data).group(1)
        base64_str = base64_data.split(',')[1]

        img_filename = f"image_{hash(base64_str) % 1_000_000}.{file_type}"
        img_path = os.path.join(image_dir, img_filename)

        with open(img_path, 'wb') as f:
            f.write(base64.b64decode(base64_str))

        return f"![{alt_text}]({img_filename})"

    new_md_content = re.sub(img_tag_pattern, replace_func, md_content)
    return new_md_content

def process_all_markdown_files(root_folder):
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith('.md'):
                md_path = os.path.join(dirpath, filename)
                with open(md_path, 'r', encoding='utf-8') as file:
                    content = file.read()

                updated_content = extract_and_save_images(content, md_path)

                with open(md_path, 'w', encoding='utf-8') as file:
                    file.write(updated_content)

                print(f"Processed: {md_path}")

# Example usage
if __name__ == "__main__":
    folder_to_process = "./examples/content"
    process_all_markdown_files(folder_to_process)
