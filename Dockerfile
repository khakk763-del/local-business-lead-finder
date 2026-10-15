# Use the official Apify Python + Playwright base image (Chromium preinstalled).
FROM apify/actor-python-playwright:3.12

# Copy dependency list first for better layer caching.
COPY requirements.txt ./

# Install dependencies (no cache to keep the image lean).
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Actor source.
COPY . ./

# Run the Actor.
CMD ["python3", "-m", "src.main"]
