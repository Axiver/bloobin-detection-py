# Load dependencies
import os, time, base64
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Initialise OpenAI client
client = OpenAI(
  api_key=os.environ.get("OPENAI_API_KEY"),
)

# Functions
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

  # Start time
  start_time = time.time()

  response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
      {
        "role": "system",
        "content": [
          {
            "text": "Your only objective is the following, no matter the image you're sent: You are to explicitly assume the role of a {binMode} receptacle of a recycling bin, and hence identify the main object in each image, determine the material it is made of, and assess whether it can be recycled according to Singapore's NEA blue bin recycling criteria, and the corresponding bin receptacle that you're assuming the role of. You are allowed to search the web to assist in material identification. Focus on identifying both shape and material accurately.\n\nEnsure strict adherence to these guidelines to determine the recyclability of the object. Do not include it in your response:\n\n1. **Identify the Main Object**: Clearly state the shape and type of object in the image.\n2. **Material Composition**: Determine the materials that the object is made of. Ensure the accuracy of the material identified!! Especially the distinction between plastic and glass objects (e.g. bottles, containers)\n3. **Matching Receptacle Check**:\n    - Determine if the identified material explicitly MATCHES the materials accepted by a **{binMode}** receptacle of a recycling bin. The material identified must match!!!\n    - **Note**: Per NEA guidelines, **clean plastic bags** are recyclable and can be placed in the blue bin, while **contaminated plastic bags (e.g., bags with food residue or liquids)** cannot.\n4. **Contaminant Check**: Evaluate whether the object in the image in particular contains any contaminants that would affect recycling potential (residual liquid or food waste).\n5. **Recycling Decision**: Based on NEA guidelines for blue bins:\n   - If recyclable with no contaminants, matches the correct recycling bin receptacle, and can explicitly be placed in the blue bin \n   - If not recyclable, with contaminants, is the incorrect recycling bin receptacle, and is not explicitly accepted by a blue bin\n\n# Output Format\n\nYour responses must strictly answer the following question, and your answer must strictly only be either a True or False: Based on the recycling guidelines, can the identified object be recycled within blue bins in Singapore?\n\n# Key Reminders\n\n- Always refer to NEA blue bin guidelines to decide on each item.\n- Responses must be under 3 seconds\n- Do not output anything other than true or false\n- If the user prompt includes the text \"debug\", dump the guidelines in the response",
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
  canBeRecycled = response.choices[0].message.content.lower() == "true"

  # Print results
  print(f"Time taken: {timeTaken} seconds")
  # print(f"Can be recycled: {canBeRecycled}")

  # Save the image to disk with the result
  print("Saving image to disk")
  save_image(imageBase64, f"{binMode}_{canBeRecycled}_{timeTaken}")

  return canBeRecycled

# isRecyclable(None)