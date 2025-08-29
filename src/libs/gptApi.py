# Load dependencies
import os, time, base64
from dotenv import load_dotenv
from openai import OpenAI
from jinja2 import Environment, FileSystemLoader

load_dotenv(verbose=True, override=True)

# Initialise OpenAI client
client = OpenAI(
  api_key=os.environ.get("OPENAI_API_KEY"),
)

BIN_MODE = os.environ.get("BIN_MODE").upper()

# Initialise Jinja2 environment
# Get the absolute path to the prompts directory relative to this script
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
prompts_dir = os.path.join(project_root, "prompts")
print(f"Obtaining prompts from: {prompts_dir}")
env = Environment(loader=FileSystemLoader(prompts_dir))

# Functions
# Load prompt from file
def load_prompt(template_name: str, **kwargs) -> str:
    template = env.get_template(template_name)
    return template.render(**kwargs)

# Encode file to base64
def base64_encode(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode("utf-8")

# Load images in base64 format
def load_images():
  # Initialise images list
  images = []

  # Iterate through images folder
  for file in os.listdir("images"):
    # Check if file is an image
    if file.endswith(".jpg") or file.endswith(".jpeg") or file.endswith(".png"):
      # Add to images list
      images.append(base64_encode(f"images/{file}"))

  return images

# Save image to disk
def save_image(imageBase64, filename):
  with open(f"results/{filename}.jpg", "wb") as image_file:
    image_file.write(base64.b64decode(imageBase64))

## Main function
def is_recyclable(imageBase64, binMode):
  # Check if image is provided
  if imageBase64 is None:
    # Obtain image to send
    images = load_images()

    # Select the first image
    imageBase64 = images[0]

  if (binMode is None):
    binMode = BIN_MODE

  # Start time
  start_time = time.time()
  if binMode == "ATM":
    promptString = load_prompt("atm.txt")
  else:
    promptString = load_prompt("detailed.txt", bin_mode=binMode)

  response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
      {
        "role": "system",
        "content": [
          {
            "text": promptString,
            "type": "text"
          }
        ]
      },
      {
        "role": "user",
        "content": [
          {
            "type": "image_url",
            "image_url": {
              "url": f"data:image/jpeg;base64,{imageBase64}",
            },
          },
        ],
      }
    ],
    temperature=0.1,
    max_tokens=2048,
    top_p=0.05,
    frequency_penalty=0,
    presence_penalty=0,
    response_format={
      "type": "text"
    }
  )

  # End time
  end_time = time.time()
  timeTaken = end_time - start_time

  # Obtain and return response
  responseContent = response.choices[0].message.content
  recyclable, identifiedMaterial, reasonForRejection = responseContent.split("_")
  print(f"Response: {responseContent}")
  canBeRecycled = recyclable.lower() == "true"

  # Print results
  print(f"Time taken: {timeTaken} seconds")
  # print(f"Can be recycled: {canBeRecycled}")

  # Save the image to disk with the result
  print("Saving image to disk")
  save_image(imageBase64, f"{binMode}_{canBeRecycled}_{timeTaken}_{identifiedMaterial}_{reasonForRejection}")

  return canBeRecycled, identifiedMaterial, reasonForRejection

# is_recyclable(None, None)