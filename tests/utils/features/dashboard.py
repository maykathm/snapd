import dash
from dash import Dash, html, dcc, Output, Input, dash_table, State, MATCH
import dash_bootstrap_components as dbc
import dash_daq as daq
import json
import os
import sys

# To ensure the unit test can be run from any point in the filesystem,
# add parent folder to path to permit relative imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import query_features as qf



suppress_callback_exceptions=True
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])


retriever = qf.DirRetriever('/home/katie/Desktop/features')
timestamps = retriever.get_sorted_timestamps_and_systems()

coverage_matrix = {}
timestamp_options = [{"label": item["timestamp"], "value": item["timestamp"]} for item in timestamps]
cached_duplicates = {}


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
            html.Div([
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
                html.Div(children="", style={'marginBottom': '10px'}),
                html.Button(
                    "🔄",
                    id='switch-button',
                    n_clicks=0,
                    style={'fontSize': '20px','padding': '4px 8px','margin': '0 10px',
                        'borderRadius': '50%','border': '1px solid #ccc','backgroundColor': 'white',
                        'cursor': 'pointer','lineHeight': '1','display': 'inline-flex',
                        'alignItems': 'center','justifyContent': 'center','width': '32px','height': '32px',
                    }
                ),
                html.Div(children="System 2", style={'marginTop': '10px', 'marginBottom': '20px'}),
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
                daq.BooleanSwitch(
                    id='remove-failed-switch',
                    label="Remove failed tests",
                ),
                daq.BooleanSwitch(
                    id='only-same-switch',
                    label='Only compare features across tests that are present in both systems',
                ),
            ], style={'width':'25%'}),
            dcc.Loading(
                html.Div(
                    id='coverage-diff-container'
                ),
            ),
        ]), id={'type': 'collapse', 'index': 2}, is_open=False
    ),
    html.Div(children="", style={'fontSize': '24px', 'marginBottom': '20px'}),
    dbc.Button("Feature coverage matrix per system comparison", id={'type': "toggle-button", 'index': 3}, n_clicks=0, className="mb-3"),
    dbc.Collapse(
        html.Div([
            html.Div(children="Calculates difference in feature coverage matrix between all systems", style={'fontSize': '20px', 'marginBottom': '20px'}),
            html.Div(children="Timestamp", style={'marginBottom': '20px'}),
            html.Div([
                dcc.Dropdown(
                    id={'type': 'timestamp-dropdown', 'index': 4},
                    options=timestamp_options,
                    placeholder="Select timestamp"
                ),
                html.Div(children="coverage data filter", style={'fontSize': '16px', 'marginTop': '20px', 'marginBottom': '20px'}),
                dcc.Dropdown(
                    id='suite-dropdown-filter',
                    options=[],
                    placeholder="Select suite",
                    clearable=True
                    ),
                dcc.Dropdown(
                    id='task-dropdown-filter',
                    options=[],
                    placeholder="Select task",
                    clearable=True
                    ),
                dcc.Dropdown(
                    id='variant-dropdown-filter',
                    options=[],
                    placeholder="Select variant",
                    clearable=True
                    ),
                daq.BooleanSwitch(
                    id='coverage-remove-failed-switch',
                    label="Remove failed tests",
                ),
            ], style={'width':'25%'}),
            dcc.Loading(
                html.Div([
                    dash_table.DataTable(
                        id='coverage-matrix-table',
                        filter_action='native',
                        sort_action='native',
                        style_cell={'textAlign': 'center', 'minWidth': '100px', 'maxWidth': '200px', 'whiteSpace': 'normal'},
                        style_table={'overflowX': 'auto', 'maxWidth': '900px', 'margin': 'auto'},
                    ),
                    html.Div(id='cell-data-container', 
                            style={'display': 'inline-block', 'marginLeft': '20px', 'verticalAlign': 'top', 'flex': 1, 'overflow': 'auto', 'maxWidth':'900px'})
                    ],
                    id='coverage-matrix-container',
                    style={
                        'display': 'flex',
                        'justifyContent': 'center',  # center the tables horizontally
                        'alignItems': 'flex-start',  # align tables at the top
                        'gap': '20px',               # gap between tables (alternative to marginLeft)
                        'maxWidth': '1900px',        # total max width to fit both tables nicely
                        'margin': 'auto'
                    }
                ),
            ),
        ]), id={'type': 'collapse', 'index': 3}, is_open=False
    ),
    html.Div(children="", style={'fontSize': '24px', 'marginBottom': '20px'}),
    dbc.Button("Duplicate features", id={'type': "toggle-button", 'index': 4}, n_clicks=0, className="mb-3"),
    dbc.Collapse(
        html.Div([
            html.Div(children="Timestamp", style={'marginBottom': '20px'}),
            dcc.Dropdown(
                id={'type': 'timestamp-dropdown', 'index': 5},
                options=timestamp_options,
                placeholder="Select timestamp"
            ),
            dcc.Dropdown(
                id={'type': 'systems-dropdown', 'index': 5},
                options=[],
                placeholder="Select system"
            ),
            html.Div([
                dcc.Loading(
                    dash_table.DataTable(
                        id='duplicate-table',
                        filter_action='native',
                        sort_action='native',
                        style_cell={'textAlign': 'center', 'minWidth': '100px', 'maxWidth': '200px', 'whiteSpace': 'normal'},
                        style_table={'overflowX': 'auto', 'maxWidth': '900px', 'margin': 'auto'},
                    ),
                ),
                html.Div(id='cell-duplicate-container', 
                        style={'display': 'inline-block', 'marginLeft': '20px', 'verticalAlign': 'top', 'flex': 1, 'overflow': 'auto', 'maxWidth':'900px'}
                )],
                id='duplicate-matrix-container',
                style={
                    'display': 'flex',
                    'justifyContent': 'center',  # center the tables horizontally
                    'alignItems': 'flex-start',  # align tables at the top
                    'gap': '20px',               # gap between tables (alternative to marginLeft)
                    'maxWidth': '1900px',        # total max width to fit both tables nicely
                    'margin': 'auto'
                }
            ),
        ]), id={'type': 'collapse', 'index': 4}, is_open=False
    ),
])


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


def get_columns_from_list_of_dicts(features):
    i, _ = max(enumerate(features), key=lambda x: len(x[1]))
    return [{"name": key, "id": key} for key in features[i].keys()]


def make_dict_table_friendly(features):
    processed = []
    for feature in features:
        feat_dict = {}
        for k, v in feature.items():
            feat_dict[k] = json.dumps(v) if isinstance(v, list) else v
        processed.append(feat_dict)
    return processed

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
    Input('remove-failed-switch', 'on'),
    Input('only-same-switch', 'on'),
)
def update_totals_table(ts_2, sys_2, ts_3, sys_3, remove_failed_value, only_same_value):
    if not ts_2 or not sys_2 or not ts_3 or not sys_3:
        return []
    
    diff = qf.diff(retriever, ts_2, sys_2, ts_3, sys_3, remove_failed_value, only_same_value)

    
    tables = []
    for feature_name, features in diff.items():
        processed = []
        for feature in features:
            feat_dict = {}
            for k, v in feature.items():
                feat_dict[k] = json.dumps(v) if isinstance(v, list) else v
            processed.append(feat_dict)
        table = dash_table.DataTable(
            data=processed, 
            columns=get_columns_from_list_of_dicts(features),
            filter_action='native',
            sort_action='native',
            style_cell={'textAlign': 'center', 'minWidth': '100px', 'maxWidth': '200px', 'whiteSpace': 'normal'},
            style_table={'overflowX': 'auto', 'maxWidth': '900px', 'margin': 'auto'},
        )
        tables.append(html.Div([html.H4(feature_name), table], style={'maxWidth': '900px', 'margin': 'auto'}))
    
    return tables


@app.callback(
    Output({'type': 'timestamp-dropdown', 'index': 2}, 'value'),
    Output({'type': 'systems-dropdown', 'index': 2}, 'value'),
    Output({'type': 'timestamp-dropdown', 'index': 3}, 'value'),
    Output({'type': 'systems-dropdown', 'index': 3}, 'value'),
    Input('switch-button', 'n_clicks'),
    State({'type': 'timestamp-dropdown', 'index': 2}, 'value'),
    State({'type': 'systems-dropdown', 'index': 2}, 'value'),
    State({'type': 'timestamp-dropdown', 'index': 3}, 'value'),
    State({'type': 'systems-dropdown', 'index': 3}, 'value'),
)
def switch_dropdown_values(n_clicks, ts2, sys2, ts3, sys3):
    if n_clicks is None or n_clicks == 0:
        # No clicks yet, do nothing
        raise dash.exceptions.PreventUpdate

    # Swap values
    return ts3, sys3, ts2, sys2


@app.callback(
    Output('suite-dropdown-filter', 'options'),
    Output('task-dropdown-filter', 'options'),
    Output('variant-dropdown-filter', 'options'),
    Input({'type': 'timestamp-dropdown', 'index': 4}, 'value'),
)
def update_systems_dropdown(selected_timestamp):
    if not selected_timestamp:
        raise dash.exceptions.PreventUpdate
    task_list = qf.task_list(retriever, selected_timestamp)
    suites = set([task.suite for task in task_list])
    tasks = set([task.task_name for task in task_list])
    variants = set([task.variant for task in task_list])
    return list(suites), list(tasks), list(variants)


@app.callback(
    Output('coverage-matrix-table', 'columns'),
    Output('coverage-matrix-table', 'data'),
    Input({'type': 'timestamp-dropdown', 'index': 4}, 'value'),
    Input('coverage-remove-failed-switch', 'on'),
    Input('suite-dropdown-filter', 'value'),
    Input('task-dropdown-filter', 'value'),
    Input('variant-dropdown-filter', 'value'),
)
def create_coverage_matrix(timestamp, remove_failed, suite, task, variant):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    
    systems = None
    for ts in timestamps:
        if ts['timestamp'] == timestamp:
            systems = ts['systems']
    if not systems:
        return [], []
    
    columns = [{"name": "System", "id": "system"}] + [{"name": key, "id": key} for key in qf.KNOWN_FEATURES]
    coverage_matrix[timestamp] = [{'system': system, **{key: 0 for key in qf.KNOWN_FEATURES}} for system in systems]
    matrix = [{'system': system, **{key: 0 for key in qf.KNOWN_FEATURES}} for system in systems]
    for i, system in enumerate(systems):
        feats = qf.feat_sys(retriever, timestamp, system, remove_failed, suite, task, variant)
        coverage_matrix[timestamp][i].update(feats)
        for feature in qf.KNOWN_FEATURES:
            matrix[i][feature] = len(feats[feature])

    return columns, matrix


@app.callback(
    Output('cell-data-container', 'children'),
    Input('coverage-matrix-table', 'active_cell'),
    State('coverage-matrix-table', 'derived_viewport_data'),
    State({'type': 'timestamp-dropdown', 'index': 4}, 'value')
)
def display_cell_data(active_cell, table_data, timestamp):
    if not active_cell or not table_data or not timestamp:
        return "Click on a cell to see feature data"

    row_idx = active_cell['row']
    col_idx = active_cell['column_id']

    # Get the system name from the row data
    system = table_data[row_idx]['system']

    system_data = next((item for item in coverage_matrix[timestamp] if item['system'] == system), None)
    if not system_data:
        return "No data found for the selected cell."
    
    features = system_data[col_idx]
    if len(features) == 0:
        return "No data found for the selected cell."
    
    table = dash_table.DataTable(
            data=make_dict_table_friendly(features),
            columns=get_columns_from_list_of_dicts(features),
            filter_action='native',
            sort_action='native',
            style_cell={'textAlign': 'center', 'minWidth': '100px', 'maxWidth': '200px', 'whiteSpace': 'normal'},
            style_table={'overflowX': 'auto', 'maxWidth': '900px', 'margin': 'auto'},
        )
    return html.Div([html.H4(f"{system} ---- {col_idx}:", style={'textAlign':'center'}), table], style={'maxWidth': '900px', 'margin': 'auto'})


@app.callback(
    Output('duplicate-table', 'columns'),
    Output('duplicate-table', 'data'),
    Input({'type': 'timestamp-dropdown', 'index': 5}, 'value'),
    Input({'type': 'systems-dropdown', 'index': 5}, 'value'),
)
def calculate_duplicate_systems(timestamp, system):

    if not timestamp or not system:
        return [], []
    
    if timestamp in cached_duplicates and system in cached_duplicates[timestamp]:
        duplicates = cached_duplicates[timestamp][system]
    else:
        duplicates = qf.dup(retriever, timestamp, system, False)
        if timestamp in cached_duplicates:
            cached_duplicates[timestamp][system] = duplicates
        else:
            cached_duplicates[timestamp] = {system: duplicates}

    columns = [{"name": "suite", "id": "suite"}, {"name": "task", "id": "task"}, {"name": "variant", "id": "variant"}]

    rows = [{"suite": d.suite, "task": d.task_name, "variant": d.variant} for d in duplicates]

    return columns, rows


@app.callback(
    Output('cell-duplicate-container', 'children'),
    Input('duplicate-table', 'active_cell'),
    State('duplicate-table', 'derived_viewport_data'),
    State({'type': 'timestamp-dropdown', 'index': 5}, 'value'),
    State({'type': 'systems-dropdown', 'index': 5}, 'value')
)
def display_duplicate_cell_data(active_cell, table_data, timestamp, system):
    if not active_cell or not table_data or not timestamp:
        return "Click on a cell to see feature data"

    row_idx = active_cell['row']

    test = table_data[row_idx]

    features = qf.feat_sys(retriever, timestamp, system, False, suite=test['suite'], task=test['task'], variant=test['variant'])

    tables = [html.H4(f"{system}:{str(qf.TaskIdVariant(test['suite'], test['task'], test['variant']))}", style={'textAlign':'center'})]
    for feature_name, feature_data in features.items():
        processed = []
        for feature in feature_data:
            feat_dict = {}
            for k, v in feature.items():
                feat_dict[k] = json.dumps(v) if isinstance(v, list) else v
            processed.append(feat_dict)
        table = dash_table.DataTable(
            data=processed, 
            columns=get_columns_from_list_of_dicts(feature_data),
            filter_action='native',
            sort_action='native',
            style_cell={'textAlign': 'center', 'minWidth': '100px', 'maxWidth': '200px', 'whiteSpace': 'normal'},
            style_table={'overflowX': 'auto', 'maxWidth': '900px', 'margin': 'auto'},
        )
        tables.append(html.Div([html.H4(feature_name), table], style={'maxWidth': '900px', 'margin': 'auto'}))
    
    return tables


if __name__ == '__main__':
    app.run(debug=False)
