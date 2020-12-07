import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

#######################################################  INDEX  #########################################################

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio = db.execute("SELECT * FROM portfolio WHERE username = (SELECT username FROM users WHERE id = ?)", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    all_cash = cash
    for row in portfolio:
        all_cash += row["total"]
    return render_template("index.html", total = all_cash, cash = cash, portfolio = portfolio)

#######################################################  BUY  #########################################################

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        symbol_data = lookup(symbol)
        user_shares = int (request.form.get("shares"))

        # Checking that symbol and shares are written correctly
        if not symbol or not symbol_data:
            return apology("MISSING SYMBOL")
        if user_shares < 1:
            return apology("MISSING SHARES")

        # if we reached here, then data written correctly. Let's deal with it
        total_price = float (symbol_data["price"] * user_shares)
        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

        # Check if user has the price to buy or not
        if total_price > user_cash[0]["cash"]:
            return apology("NO ENOUGH CASH")

        # Proceeding buy
        username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
        user_cash[0]["cash"] -= total_price
        db.execute("UPDATE users SET cash = ? WHERE id = ?",user_cash[0]["cash"], session["user_id"])

        # Add this to history
        db.execute("INSERT INTO history (symbol, shares, price, username) VALUES (?, ?, ?, ?)",
                    symbol_data["symbol"], user_shares, symbol_data["price"], username)

        # Adding to Portfolio
        portfolio_shares = db.execute("SELECT SUM(shares) FROM portfolio WHERE username = ? AND symbol = ?",
                                       username, symbol_data["symbol"])[0]["SUM(shares)"]

        if not portfolio_shares:  # Then it's the first time
            db.execute("INSERT INTO portfolio (username, symbol, name, shares, price, total) VALUES (?, ?, ?, ?, ?, ?)",
                        username, symbol_data["symbol"], symbol_data["name"], user_shares, symbol_data["price"], total_price)

        else:  # Increasing shares
            db.execute("UPDATE portfolio SET shares = ?, total = total + ? WHERE symbol = ? AND username = ?",
                        portfolio_shares + user_shares, total_price, symbol_data["symbol"], username)

        return redirect("/")
    else:
        return render_template("buy.html")

#######################################################  HISTORY  #########################################################

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM history WHERE username = (SELECT username FROM users WHERE id = ?)", session["user_id"])
    return render_template("history.html", history = history)

#######################################################  LOGIN  #########################################################

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username = request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

#######################################################  LOGOUT  #########################################################

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

#######################################################  QUOTE  #########################################################

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        result = lookup(request.form.get("symbol"))
        if result != None:
            return render_template("quoted.html", result = result)
        else:
            return apology("Symbol Doesn't Exist")
    else:
        return render_template("quote.html")

#######################################################  REGISTER  #########################################################

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Ensure username was submitted
    if request.method == "POST":
        pass_hash = generate_password_hash(request.form.get("password"))
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirm was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 403)

        # Ensure two passwords match
        elif not check_password_hash(pass_hash, request.form.get("confirmation")):
            return apology("passwords don't match", 403)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

    db.execute("INSERT INTO users (username, hash) VALUES(?,?)", (request.form.get("username"), pass_hash))

    return render_template("registered.html")

#######################################################  SELL  #########################################################

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_symbols = db.execute("SELECT symbol FROM portfolio WHERE username = (SELECT username FROM users WHERE id = ?)", session["user_id"])

    if request.method == "POST":

        symbol = request.form.get("symbol")
        symbol_data = lookup(symbol)
        shares_to_sell = int (request.form.get("shares")) # required to sell

        # Checking that symbol and shares are written correctly
        if not symbol or not symbol_data:
            return apology("MISSING SYMBOL")
        if shares_to_sell < 1:
            return apology("MISSING SHARES")

        # Ensuring that he has number of shares >= to-be-sold shares
        current_shares = db.execute("SELECT shares FROM portfolio WHERE username = (SELECT username FROM users WHERE id = ?) AND symbol = ?",
                                     session["user_id"], symbol_data["symbol"])[0]["shares"]
        if shares_to_sell > current_shares:
            return apology("YOU DON'T OWN THESE SHARES")

        # Then he wrote everything correctly
        total_price = float (symbol_data["price"] * shares_to_sell)
        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

        # Proceeding Sell
        username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
        user_cash[0]["cash"] += total_price
        db.execute("UPDATE users SET cash = ? WHERE id = ?",user_cash[0]["cash"], session["user_id"])

        # Add this to history
        db.execute("INSERT INTO history (symbol, shares, price, username) VALUES (?, ?, ?, ?)",
                    symbol_data["symbol"], (-1) * shares_to_sell, symbol_data["price"], username)

        # Adding to Portfolio
        portfolio_shares = db.execute("SELECT SUM(shares) FROM portfolio WHERE username = ? AND symbol = ?",
                                       username, symbol_data["symbol"])[0]["SUM(shares)"]

        # Decreasing shares
        db.execute("UPDATE portfolio SET shares = ?, total = total - ? WHERE symbol = ? AND username = ?",
                    portfolio_shares - shares_to_sell, total_price, symbol_data["symbol"], username)

        db.execute("DELETE FROM portfolio WHERE shares = 0")

        return redirect("/")
    else:
        return render_template("sell.html", symbols = user_symbols)

########################################################################################################################
def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
