from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tickets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------------------
# Database models
# -------------------------------
class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String, nullable=False)
    event_count = db.Column(db.Integer, nullable=False)
    players = db.relationship('Player', backref='ticket', cascade="all, delete-orphan")

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    pairs = db.relationship('Pair', backref='player', cascade="all, delete-orphan")

class Pair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    match = db.Column(db.String, nullable=False)
    odd = db.Column(db.String)
    status = db.Column(db.String, nullable=False)

# Create tables
with app.app_context():
    db.create_all()

# -------------------------------
# Selenium scraping functions
# -------------------------------
def extract_ticket_id(url):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" in qs:
        return qs["id"][0]
    m = re.search(r"id=([^&]+)", url)
    return m.group(1) if m else None

def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
    )
    return webdriver.Chrome(options=options)

def detect_status(row):
    try:
        svg = row.find_element(By.TAG_NAME, "svg")
        paths = svg.find_elements(By.TAG_NAME, "path")
        for p in paths:
            fill = p.get_attribute("fill")
            if not fill:
                continue
            fill = fill.lower()
            if "#22c55e" in fill or "green" in fill:
                return "won"
            if "#ef4444" in fill or "red" in fill:
                return "lost"
        return "pending"
    except:
        return "pending"

def scrape_ticket(url):
    driver = create_driver()
    events = []

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h3")))
        time.sleep(3)

        rows = driver.find_elements(By.XPATH, "//h3/ancestor::div[3]")
        for row in rows:
            try:
                match_el = row.find_element(By.TAG_NAME, "h3")
                match = match_el.get_attribute("data-tooltip") or match_el.text
                if "-" not in match:
                    continue
                odd = None
                divs = row.find_elements(By.TAG_NAME, "div")
                for d in divs:
                    txt = d.text.strip()
                    if re.match(r"^\d+\.\d+$", txt):
                        odd = txt
                        break
                status = detect_status(row)
                events.append({
                    "match": match,
                    "odd": odd,
                    "status": status
                })
            except:
                pass
    finally:
        driver.quit()

    players = []
    for i in range(0, len(events), 2):
        players.append({
            "player": (i // 2) + 1,
            "pairs": events[i:i+2]
        })

    return {"event_count": len(events), "players": players}

# -------------------------------
# Flask routes
# -------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scrape", methods=["POST"])
def scrape():
    url = request.json.get("url")
    result = scrape_ticket(url)

    # Save to database
    ticket = Ticket(url=url, event_count=result['event_count'])
    db.session.add(ticket)
    db.session.commit()  # Commit to get ticket.id

    for p in result['players']:
        player = Player(ticket_id=ticket.id, number=p['player'])
        db.session.add(player)
        db.session.commit()
        for pair in p['pairs']:
            pair_row = Pair(
                player_id=player.id,
                match=pair['match'],
                odd=pair['odd'],
                status=pair['status']
            )
            db.session.add(pair_row)
    db.session.commit()

    return jsonify(result)

@app.route("/tickets")
def view_tickets():
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    return render_template("tickets.html", tickets=tickets)

if __name__ == "__main__":
    app.run(debug=True)