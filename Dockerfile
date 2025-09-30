# Stage 1: Build the base image with Python and dependencies
FROM python:3.12-slim as builder

# Set the working directory
WORKDIR /app

# Install poetry for dependency management
RUN pip install poetry

# Copy only the files needed for dependency installation
COPY poetry.lock pyproject.toml ./

# Install dependencies using poetry, without creating a virtualenv
RUN poetry config virtualenvs.create false && poetry install --no-dev --no-root

# Stage 2: Create the final, smaller production image
FROM python:3.12-slim

WORKDIR /app

# Copy the installed dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8081

# Command to run the application using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]