import base64

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string

# Example usage
if __name__ == "__main__":
    image_path = "./examples/JanusAI Pics/pictureoffboarding.png"  # Replace with your image file
    base64_string = "![Alt Text](data:image/jpg;base64,"
    base64_string += image_to_base64(image_path)
    base64_string += ")"
    
    
    print(base64_string)
