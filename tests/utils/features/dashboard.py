import dash
from dash import Dash, html, dcc, Output, Input, dash_table, State, MATCH
import dash_bootstrap_components as dbc
import json
import os
import sys

# To ensure the unit test can be run from any point in the filesystem,
# add parent folder to path to permit relative imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import query_features as qf

retriever = qf.DirRetriever('/home/katie/Desktop/features')
timestamps = retriever.get_sorted_timestamps_and_systems()


suppress_callback_exceptions=True
# app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app = Dash(external_stylesheets=[dbc.themes.BOOTSTRAP])

timestamp_options = [{"label": item["timestamp"], "value": item["timestamp"]} for item in timestamps]

def calculate_feature_diff(selected_ts):
    for timestamp in timestamps:
        if timestamp['timestamp'] != selected_ts:
            continue
        diff_data = []
        for system in timestamp['systems']:
            diff = qf.diff_all_features(retriever, selected_ts, system, False)
            d = {key: len(value) for key, value in diff.items()}
            d['system'] = system
            diff_data.append(d)
        return diff_data


app.layout = html.Div([
    html.Div(children="", style={'fontSize': '24px', 'marginBottom': '20px'}),
    dbc.Button("Systems coverage vs. all features", id={'type': "toggle-button", 'index': 1}, n_clicks=0, className="mb-3"),
    dbc.Collapse(
        html.Div([
            dcc.Dropdown(
                id={'type': 'timestamp-dropdown', 'index': 1},
                options=timestamp_options,
                placeholder="Select timestamp"
            ),
            dcc.Dropdown(
                id={'type': 'systems-dropdown', 'index': 1},
                options=[],
                placeholder="Select system"
            ),
            html.Div(
                dash_table.DataTable(
                    id='totals-table',
                    columns=[],
                    data=[],
                    active_cell=None,
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left', 'padding': '5px'},
                    style_header={'backgroundColor': 'lightgrey', 'fontWeight': 'bold'}
                ),
                id='table-container',
                style={'display': 'block', 'marginTop': '10px'}
            ),
            html.Div(id='details-output', style={'marginTop': '20px'}),
        ]), id={'type': 'collapse', 'index': 1}, is_open=False
    ),
    html.Div(children="", style={'fontSize': '24px', 'marginBottom': '20px'}),
    dbc.Button("Compare feature coverage between systems", id={'type': "toggle-button", 'index': 2}, n_clicks=0, className="mb-3"),
    dbc.Collapse(
        html.Div([
            html.Div(children="Calculates difference in coverage between set(system_1_features) - set(system_2_features)", style={'fontSize': '20px', 'marginBottom': '20px'}),
            html.Div(children="System 1", style={'marginBottom': '20px'}),
            dcc.Dropdown(
                id={'type': 'timestamp-dropdown', 'index': 2},
                options=timestamp_options,
                placeholder="Select timestamp"
            ),
            dcc.Dropdown(
                id={'type': 'systems-dropdown', 'index': 2},
                options=[],
                placeholder="Select system"
            ),
            html.Div(children="System 2", style={'marginTop': '20px', 'marginBottom': '20px'}),
            dcc.Dropdown(
                id={'type': 'timestamp-dropdown', 'index': 3},
                options=timestamp_options,
                placeholder="Select timestamp"
            ),
            dcc.Dropdown(
                id={'type': 'systems-dropdown', 'index': 3},
                options=[],
                placeholder="Select system"
            ),
            html.Div(
                id='coverage-diff-container'
            ),
        ]), id={'type': 'collapse', 'index': 2}, is_open=False
    ),
    html.Div(children="", style={'fontSize': '24px', 'marginBottom': '20px'}),
    dbc.Button("Feature coverage matrix per system comparison", id={'type': "toggle-button", 'index': 3}, n_clicks=0, className="mb-3"),
    dbc.Collapse(
        html.Div([
            html.Div(children="Calculates difference in feature coverage matrix between all systems", style={'fontSize': '20px', 'marginBottom': '20px'}),
            html.Div(children="Timestamp", style={'marginBottom': '20px'}),
            dcc.Dropdown(
                id={'type': 'timestamp-dropdown', 'index': 4},
                options=timestamp_options,
                placeholder="Select timestamp"
            ),
            html.Div(
                id='coverage-matrix-container'
            ),
        ]), id={'type': 'collapse', 'index': 3}, is_open=False
    ),
])

@app.callback(
    Output({'type': 'collapse', 'index': MATCH}, "is_open"),
    Input({'type': 'toggle-button', 'index': MATCH}, "n_clicks"),
    State({'type': 'collapse', 'index': MATCH}, "is_open"),
)
def toggle_collapse(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

@app.callback(
    Output({'type': 'systems-dropdown', 'index': MATCH}, 'options'),
    Input({'type': 'timestamp-dropdown', 'index': MATCH}, 'value'),
)
def update_systems_dropdown(selected_timestamp):
    if not selected_timestamp:
        return []
    for item in timestamps:
        if item["timestamp"] == selected_timestamp:
            return [{"label": sys, "value": sys} for sys in item["systems"]]
    return []


@app.callback(
    Output('totals-table', 'columns'),
    Output('totals-table', 'data'),
    Input({'type': 'timestamp-dropdown', 'index': 1}, 'value')
)
def update_totals_table(selected_timestamp):
    if not selected_timestamp:
        return [], []
    
    diff_data = calculate_feature_diff(selected_timestamp)

    columns = [{"name": "System", "id": "system"}] + [{"name": key, "id": key} for key in qf.KNOWN_FEATURES]

    return columns, diff_data


@app.callback(
    Output('details-output', 'children'),
    Input('totals-table', 'active_cell'),
    State('totals-table', 'columns'),
    State('totals-table', 'data')
)
def display_column_details(active_cell, columns, data):
    if active_cell is None:
        return "Click a column cell to see details."

    col_idx = active_cell['column']
    col_id = columns[col_idx]['id']

    # If user clicked on the "system" column, ignore or handle differently
    if col_id == 'system':
        return "Please click on a total column to see details."

    # Extract details for the clicked column
    details_list = []
    for row in data:
        system = row['system']
        value = row.get(col_id, 'N/A')
        details_list.append(html.Div(f"{system}: {value}"))

    return html.Div([
        html.H4(f"Details for column: {col_id}"),
        *details_list
    ])

@app.callback(
    Output('coverage-diff-container', 'children'),
    Input({'type': 'timestamp-dropdown', 'index': 2}, 'value'),
    Input({'type': 'systems-dropdown', 'index': 2}, 'value'),
    Input({'type': 'timestamp-dropdown', 'index': 3}, 'value'),
    Input({'type': 'systems-dropdown', 'index': 3}, 'value'),
)
def update_totals_table(ts_2, sys_2, ts_3, sys_3):
    if not ts_2 or not sys_2 or not ts_3 or not sys_3:
        return []
    
    diff = qf.diff(retriever, ts_2, sys_2, ts_3, sys_3, False, False)

    
    tables = []
    for feature_name, features in diff.items():
        columns = [{"name": key, "id": key} for key in features[0].keys()]
        processed = []
        for feature in features:
            feat_dict = {}
            for k, v in feature.items():
                feat_dict[k] = json.dumps(v) if isinstance(v, list) else v
            processed.append(feat_dict)
        table = dash_table.DataTable(
            data=processed, 
            columns=columns,
            style_cell={'textAlign': 'center', 'minWidth': '100px', 'maxWidth': '200px', 'whiteSpace': 'normal'},
            style_table={'overflowX': 'auto', 'maxWidth': '900px', 'margin': 'auto'},
        )
        tables.append(html.Div([html.H4(feature_name), table], style={'maxWidth': '900px', 'margin': 'auto'}))
    
    return tables


@app.callback(
    Output('coverage-matrix-container', 'children'),
    Input({'type': 'timestamp-dropdown', 'index': 4}, 'value'),
)
def create_coverage_matrix(timestamp):
    pass

    # if not selected_timestamp:
    #     return [], []
    
    # diff_data = calculate_feature_diff(selected_timestamp)

    # columns = [{"name": "System", "id": "system"}] + [{"name": key, "id": key} for key in qf.KNOWN_FEATURES]

    # return columns, diff_data

# @app.callback(
#     Output('collapsed-state', 'data'),
#     Input('toggle-table-btn', 'n_clicks'),
#     Input('totals-table', 'active_cell'),
#     State('collapsed-state', 'data'),
#     State('totals-table', 'columns')
# )
# def update_collapsed_state(n_clicks, active_cell, collapsed, columns):
#     ctx = dash.callback_context

#     if not ctx.triggered:
#         return collapsed

#     triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

#     # If user clicked a total column cell -> collapse table
#     if triggered_id == 'totals-table' and active_cell is not None:
#         col_idx = active_cell['column']
#         # Check if clicked column is NOT the 'system' column
#         if columns and columns[col_idx]['id'] != 'system':
#             return True  # Collapse table

#     # If user clicked toggle button -> toggle collapse state
#     if triggered_id == 'toggle-table-btn':
#         return not collapsed

#     return collapsed

# @app.callback(
#     Output('table-container', 'style'),
#     Input('collapsed-state', 'data')
# )
# def toggle_table_visibility(collapsed):
#     if collapsed:
#         return {'display': 'none', 'marginTop': '10px'}
#     else:
#         return {'display': 'block', 'marginTop': '10px'}

if __name__ == '__main__':
    app.run(debug=False)
