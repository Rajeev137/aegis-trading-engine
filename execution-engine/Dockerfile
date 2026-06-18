# Use a lightweight Python image
FROM python:3.12-slim

# Prevent Python from writing .pyc files to disc and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies (required for some Python packages like asyncpg)
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the API port
EXPOSE 8000

# The default command will run the FastAPI server
# (We will override this command in docker-compose for the background worker)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]