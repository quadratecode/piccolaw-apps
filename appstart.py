from pywebio import *
import EmplawApp
import DeadlineApp


# --- DEPLOYMENT --- #
# Import apps as module, then add to start_server
# Access via http://host:port/?app=XXX
if __name__ == '__main__':
    start_server(
        [EmplawApp.emplaw_app, DeadlineApp.deadline_app], # Add apps to dictionary
        port=41780,
        host="0.0.0.0",
        debug=False)
