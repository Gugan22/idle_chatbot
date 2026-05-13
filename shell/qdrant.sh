podman --version

podman machine list

podman machine start

podman pull docker.io/qdrant/qdrant:latest

podman images

podman volume create qdrant_storage

podman volume ls

podman run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage docker.io/qdrant/qdrant:latest

podman ps

curl http://localhost:6333

podman logs -f insurance-qdrant

#___________________________________________________________________________________________


# Stop Qdrant
podman stop insurance-qdrant

# Start it again
podman start insurance-qdrant

# Restart
podman restart insurance-qdrant

# Live resource usage (CPU, RAM)
podman stats insurance-qdrant

# Remove container (data stays in the volume)
podman rm insurance-qdrant

# List volumes
podman volume ls

# WARNING: this deletes all Qdrant data permanently
podman volume rm qdrant_storage

# Stop the Podman machine when done for the day
podman machine stop