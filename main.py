from pywebio import *
import app_employment_law.emplaw_app as emplaw_app
import app_deadline_calculator.deadline as deadline


# --- DEPLOYMENT --- #
# Import apps as module, then add to start_server
# Access via http://host:port/?app=XXX
if __name__ == "__main__":
    start_server(
        [emplaw_app.emplaw_app, deadline.deadline_app],  # Add apps to dictionary
        port=41780,
        host="0.0.0.0",
        debug=False,
    )
