"""
Epitopes Data Editor - PyShiny App

Sample usage of the table_editor widget module with multiple tabs.
Core implementation: src/ui.py, src/server.py

Demonstrates using the table editor as a reusable widget in a tabbed interface.
Each tab can use its own config file pointing to different data sources.

Usage:
    # Single config (default):
    table_editor_ui("editor1")
    table_editor_server("editor1")
    
    # Multiple configs for different tables:
    table_editor_ui("editor1", config_path="configs/epitopes_config.json")
    table_editor_ui("editor2", config_path="configs/genes_config.json")
    
    table_editor_server("editor1", config_path="configs/epitopes_config.json")
    table_editor_server("editor2", config_path="configs/genes_config.json")

Config file structure:
    Each config file must specify:
    - database.connection_string: PostgreSQL connection
    - database.data_table: Table name to load
    - database.mods_table: Modifications table name
    - table.primary_key: Primary key column(s)
    - table.title: Display title for the tab
"""

from shiny import App, ui
from src.widgets import table_editor_ui, table_editor_server


# Define config paths for each tab
PRIMARY_CONFIG = "app_config.json"        # Epitopes Table
CLONE_CONFIG = "app_config_clone.json"    # Epitopes Clone (demo)


# App UI with tabbed interface for multiple table editors
app_ui = ui.page_fluid(
    ui.navset_tab(
        ui.nav_panel(
            "Epitopes Table",
            table_editor_ui("editor1", config_path=PRIMARY_CONFIG),
        ),
        ui.nav_panel(
            "Epitopes Clone",
            table_editor_ui("editor2", config_path=CLONE_CONFIG),
        ),
        id="main_tabs",
    ),
)


# App server - initialize table editors with their configs
def server(input, output, session):
    table_editor_server("editor1", config_path=PRIMARY_CONFIG)
    table_editor_server("editor2", config_path=CLONE_CONFIG)


# Create the app
app = App(app_ui, server)
