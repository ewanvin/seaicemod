import os
import sys

# Get the root directory of the app 
app_root = os.getenv('APP_ROOT')
# Add the directory containing toolkit.py to the system path
sys.path.append(os.path.join(app_root, 'bokeh-app'))

import panel as pn
from bokeh.plotting import figure
from bokeh.models import HoverTool, Paragraph, LegendItem, Legend, DatetimeAxis
import logging
import param
import toolkit as tk
from bokeh.palettes import viridis, cividis, plasma, Category10
from bokeh.colors import RGB
from bokeh.transform import linear_cmap
import xarray as xr
import numpy as np 
import pandas as pd

# Specify a loading spinner wheel to display when data is being loaded
pn.extension(loading_spinner='dots', loading_color='#696969')

def exception_handler(ex):
    # Function used to handle exceptions by showing an error message to the user
    logging.error('Error', exc_info=ex)
    pn.state.notifications.error(f'{ex}')

# Handle exceptions
pn.extension('notifications')
pn.extension(exception_handler=exception_handler, notifications=True)

# Define color palettes
model_palette = Category10[10]  
ssp_scenarios = ['ssp126', 'ssp245', 'ssp370', 'ssp460', 'ssp585']
number_of_colors = max(256, len(ssp_scenarios) * len(model_palette))
scenario_palette = viridis(len(ssp_scenarios))

# Generate color palettes with a specific number of colors
def generate_palette(palette_func, num_colors):
    return palette_func(num_colors)

color_groups = {
    'Sequential color maps': {
        'Viridis': generate_palette(viridis, len(ssp_scenarios)),
        'Viridis (reversed)': list(reversed(generate_palette(viridis, len(ssp_scenarios)))),
        'Plasma': generate_palette(plasma, len(ssp_scenarios)),
        'Plasma (reversed)': list(reversed(generate_palette(plasma, len(ssp_scenarios)))),
        'Cividis': generate_palette(cividis, len(ssp_scenarios)),
        'Cividis (reversed)': list(reversed(generate_palette(cividis, len(ssp_scenarios)))),
    },
    'Non-sequential color maps': {
        'Category10': Category10[10],
    }
}

class SeaIceAnalysis(param.Parameterized):
    color_scale_selector = param.Selector(objects=list(color_groups['Sequential color maps'].keys()) + list(color_groups['Non-sequential color maps'].keys()), default='Viridis')
    variable = param.Selector(objects=['siarean', 'siextentn'], default='siarean')
    temporal_resolution = param.Selector(objects=['Monthly', 'Daily', 'Seasonal', 'Yearly'], default='Monthly')
    models = param.ListSelector(objects=[
        'NorESM2-LM_sea_ice', 
        'MRI-ESM2-0_sea_ice', 
        'MIROC6_sea_ice', 
        'EC-Earth3-Veg_sea_ice', 
        'CanESM5_sea_ice', 
        'ACCESS-CM2_sea_ice'], 
        default=['NorESM2-LM_sea_ice'])
    scenarios = param.ListSelector(objects=ssp_scenarios, default=['ssp126'])
    
    # Add selection of months when selecting Seasonal reso
    #season_months = param.ListSelector(objects=['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'], default=['January', 'February', 'March'])
    season_months = param.ListSelector(objects=['DJF','MAM','JJA','SON'], default=['DJF'])


    def __init__(self, **params):
        super().__init__(**params)
        self.data_info = None
        self.figure = figure(title="Sea Ice Analysis", x_axis_label='Year', y_axis_label='1e6 km2', x_axis_type='datetime')#, width=1500, height=800)
        self.figure.ygrid.grid_line_color = 'black'
        self.figure.xgrid.grid_line_color = 'black'
        self.figure.ygrid.grid_line_alpha = 0.2
        self.figure.xgrid.grid_line_alpha = 0.2
        self.figure.sizing_mode = 'stretch_both'


        # Adding osisaf data
        self.constant_dataset = xr.open_dataset('https://thredds.met.no/thredds/dodsC/osisaf/met.no/ice/index/v2p2/nh/osisaf_nh_sia_monthly.nc')
        self.constant_time = self.constant_dataset.time.values 
        self.constant_values = self.constant_dataset['sia'].values


        self.season_months_widget = pn.Param(self.param.season_months, widgets={'season_months': pn.widgets.CheckBoxGroup})
        self.update_season_selector_visibility()
        self.update_plot() # Initialize the plot with default parameters



    @param.depends('color_scale_selector', watch=True)
    def update_color_palette(self):
        selected_palette = self.color_scale_selector
        if selected_palette in color_groups['Sequential color maps']:
            self.color_palette = color_groups['Sequential color maps'][selected_palette]
        else:
            self.color_palette = color_groups['Non-sequential color maps'][selected_palette]

        # Ensure the color palette has enough colors for all combinations of models and scenarios
        total_combinations = len(self.models) * len(self.scenarios)
        if total_combinations > len(self.color_palette):
            self.color_palette = generate_palette(viridis, total_combinations)
    


    @param.depends('variable', 'models', 'temporal_resolution', 'scenarios', 'color_scale_selector', 'season_months', watch=True)
    def update_plot(self):
        # Update the color palette based on the selected color scale
        self.update_color_palette()

        # Clear the figure and legend items
        self.figure.renderers = []
        self.figure.legend.items = []

        legend_items = []
        added_osisaf_legends = set()  # Set to track added OSISAF legends


        # Plot the constant dataset
        line = self.figure.line(self.constant_time, self.constant_values, legend_label="Osisaf", line_width=2, color="black")
        legend_items.append(LegendItem(label="Osisaf", renderers=[line]))

        color_index = 0
        for model_index, model in enumerate(self.models):
            for scenario_index, scenario in enumerate(self.scenarios):
                try:
                    # Download and extract data
                    self.data_info = tk.download_and_extract_data(self.variable, model, 'Monthly', scenario) #self.temporal_resolution,
                    if self.data_info is None:
                        raise ValueError("Data could not be loaded.")
                    

                    # Get color for the model and scenario
                    scenario_color = self.color_palette[color_index % len(self.color_palette)]
                    color_index += 1

                    # Set xr.DataArray
                    da = self.data_info['da']

                    
                    # Group by year and season, and calculate mean OSISAF data 
                    osisaf = self.constant_dataset.copy()
                    #print(osisaf)
                    osisaf.coords['year'] = osisaf.time.dt.year
                    osisaf.coords['season'] = osisaf.time.dt.season
                    osisaf_season_mean = osisaf['sia'].groupby(['year','season']).mean()


                    # Group by year and season, and calculate mean MODEL data
                    da.coords['year'] = da.time.dt.year
                    da.coords['season'] = da.time.dt.season
                    season_mean = da.groupby(['year', 'season']).mean()
                                        

                    if self.temporal_resolution == 'Seasonal':
                        # Define season-to-month mapping
                        season_to_months = {
                            'DJF': [12, 1, 2],
                            'MAM': [3, 4, 5],
                            'JJA': [6, 7, 8],
                            'SON': [9, 10, 11]
                        }
                        season_to_line_dash = {
                        'DJF': 'solid',
                        'MAM': 'dotted',
                        'JJA': 'dashdot',
                        'SON': 'dotdash'
                        }

                        selected_seasons = self.season_months
                        
                        # Remove OSISAF data from the original line plot
                        line.visible = False

                        for season in selected_seasons:
                            months = season_to_months[season]
                            line_dash = season_to_line_dash[season]

                            # Group by year and selected months, and calculate mean OSISAF data 
                            osisaf = self.constant_dataset.copy()
                            osisaf.coords['year'] = osisaf.time.dt.year
                            osisaf.coords['month'] = osisaf.time.dt.month
                            osisaf_selected_months_mean = osisaf['sia'].sel(time=osisaf.time.dt.month.isin(months)).groupby('year').mean()

                            # Group by year and selected months, and calculate mean MODEL data
                            da.coords['year'] = da.time.dt.year
                            da.coords['month'] = da.time.dt.month
                            selected_months_mean = da.sel(time=da.time.dt.month.isin(months)).groupby('year').mean()

                            # Prepare data for plotting
                            osi_season_values = osisaf_selected_months_mean.values
                            osi_season_years = osisaf_selected_months_mean.year.values
                            osi_season_dates = [pd.Timestamp(year=int(year), month=months[0], day=1) for year in osi_season_years]
                            osi_season_dates = pd.to_datetime(osi_season_dates, format='%Y-%m-%d')

                            season_values = selected_months_mean.values
                            season_years = selected_months_mean.year.values
                            season_dates = [pd.Timestamp(year=int(year), month=months[0], day=1) for year in season_years]
                            season_dates = pd.to_datetime(season_dates, format='%Y-%m-%d')

                            # Ensure the data is 1D for each season
                            if season_values.ndim > 1 and season_values.shape[1] > 1:
                                season_values = season_values[:, 0]

                            # Plot the seasonal OSISAF data (only add legend once)
                            if f'Seasonal OSISAF {season}' not in added_osisaf_legends:
                                osi_point = self.figure.line(osi_season_dates, osi_season_values, legend_label=f'OSISAF {season}', line_width=3, color='black', line_dash=line_dash)
                                legend_items.append(LegendItem(label=f'OSISAF {season}', renderers=[osi_point]))
                                added_osisaf_legends.add(f'Seasonal OSISAF {season}')

                            # Plot the seasonal MODEL data
                            point = self.figure.line(season_dates, season_values, legend_label=f'{model} - {scenario} {season}', line_width=2, color=scenario_color, line_dash=line_dash)
                            legend_items.append(LegendItem(label=f'{model} - {scenario} {season}', renderers=[point]))
                            
                

                    elif self.temporal_resolution == 'Yearly':
                        # Removing OSISAF data from the original line plot
                        line.visible = False
                        
                        # Resampling to yearly resolution
                        yearly_osi_sia = self.constant_dataset['sia'].resample(time='YE').mean()
                        yearly_da = da.resample(time='YE').mean()

                        # Exclude the last value from yearly_osi_sia 
                        yearly_osi_sia = yearly_osi_sia[:-1]

                        # Ensure the data is 1D for each year
                        if yearly_da.ndim > 1 and yearly_da.shape[1] > 1:
                            yearly_da = yearly_da[:, 0]

                        # Plotting yearly OSISAF data (only add legend once)
                        if 'Yearly OSISAF' not in added_osisaf_legends:
                            osi_yearly = self.figure.line(yearly_osi_sia.time, yearly_osi_sia.values, legend_label='Yearly OSISAF', line_width=3, color='black')
                            legend_items.append(LegendItem(label='Yearly OSISAF', renderers=[osi_yearly]))
                            added_osisaf_legends.add('Yearly OSISAF')

                        
                        # Plot the yearly MODEL data
                        mod_yearly = self.figure.line(yearly_da.time, yearly_da.values, legend_label=f'{model} - {scenario} Yearly', line_width=2, color=scenario_color)
                        legend_items.append(LegendItem(label=f'{model} - {scenario} Yearly', renderers=[mod_yearly]))

                    

                    else:
                        time = da.time.values
                        values = da.values
                                       
                    
                    line = self.figure.line(time, values, legend_label=f"{model} - {scenario}", line_width=2, color=scenario_color)
                    legend_items.append(LegendItem(label=f"{model} - {scenario}", renderers=[line]))
                    
                    
                except Exception as e:
                    logging.error(f"An error occurred while processing {model} - {scenario}: {e}")
    
        # Create a new legend with the updated items
        if self.figure.renderers:
            self.figure.legend.items = legend_items
            self.figure.legend.title = "Legend"
            self.figure.legend.location = "bottom_left"
            self.figure.legend.click_policy = "hide"
            self.figure.legend.label_text_font_size = "10pt"
            self.figure.legend.background_fill_alpha = 0
    

    @param.depends('temporal_resolution', watch=True)
    def update_view(self):
        self.view_pane = self.view()

    
    @param.depends('temporal_resolution', watch=True)
    def update_season_selector_visibility(self):
        if self.temporal_resolution == 'Seasonal':
            self.season_months_widget.visible = True
        else:
            self.season_months_widget.visible = False


    def view(self):
        
        # Create the widgets
        widgets = {
            'color_scale_selector': pn.widgets.Select,
            'variable': pn.widgets.Select,
            'temporal_resolution': pn.widgets.Select,
            'models': pn.widgets.CheckBoxGroup,
            'scenarios': pn.widgets.CheckBoxGroup,
            'season_months': pn.widgets.CheckBoxGroup,
        }
        
                
        # Add the widgets and the figure to the layout
        widget_layout = pn.Column(
            pn.pane.Markdown("### Color Scale Selector"),
            pn.Param(self.param.color_scale_selector, widgets={'color_scale_selector': pn.widgets.Select}),
            pn.pane.Markdown("### Variable"),
            pn.Param(self.param.variable, widgets={'variable': pn.widgets.Select}),
            pn.pane.Markdown("### Temporal Resolution"),
            pn.Param(self.param.temporal_resolution, widgets={'temporal_resolution': pn.widgets.Select}),
            pn.pane.Markdown("### Models"),
            pn.Param(self.param.models, widgets={'models': pn.widgets.CheckBoxGroup}),
            pn.pane.Markdown("### Scenarios"),
            pn.Param(self.param.scenarios, widgets={'scenarios': pn.widgets.CheckBoxGroup}),
            pn.pane.Markdown("### Season Selector"),
            pn.Param(self.param.season_months, widgets={'season_months': pn.widgets.CheckBoxGroup})
        )

        return pn.Row(widget_layout, self.figure)

        

sea_ice_analysis = SeaIceAnalysis()
pn.serve(sea_ice_analysis.view, title='Sea Ice Analysis')
