"""
PyShiny App for Epitopes Data Editing with Modification Tracking
Renders a table based on tab_config.json and allows editing with JSON logging

This is the main entry point - UI and Server are separated into their own modules.
"""

from shiny import App

from ui import app_ui
from server import create_server
from config import (
    get_modification_status,
    get_all_modification_statuses,
)


# Create the app (module level for Shiny)
app = App(app_ui, create_server)
