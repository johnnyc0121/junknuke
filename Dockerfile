FROM python:3.14.6-trixie

# Install updates
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up the working directory
WORKDIR /app

# Copy package and requirements
COPY junknuke/ ./junknuke/
COPY junknuke/requirements.txt .

# Set up Python environment
RUN pip3 install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Data directory for token, processed cache, and logs
# Mount this as a volume: ./data:/app/data
RUN mkdir -p /app/data

# Execute the application
CMD ["python", "-m", "junknuke.main"]
