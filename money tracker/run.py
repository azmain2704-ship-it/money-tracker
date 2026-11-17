"""Start the app:  python run.py   then open http://127.0.0.1:5000"""
from tracker import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
