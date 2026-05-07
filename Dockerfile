FROM python:3.11-slim

WORKDIR /app

# Install dependencies before copying the rest of the app to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the standard FastAPI port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
