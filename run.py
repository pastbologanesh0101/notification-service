"""Dev entrypoint: `python run.py` starts the Flask app on localhost:5000."""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
