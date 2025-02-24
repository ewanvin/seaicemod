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
    temporal_resolution = param.Selector(objects=['Monthly', 'Daily'], default='Monthly')
    models = param.ListSelector(objects=[
        'NorESM2-LM_sea_ice', 
        'MRI-ESM2-0_sea_ice', 
        'MIROC6_sea_ice', 
        'EC-Earth3-Veg_sea_ice', 
        'CanESM5_sea_ice', 
        'ACCESS-CM2_sea_ice'], 
        default=['NorESM2-LM_sea_ice'])
    scenarios = param.ListSelector(objects=ssp_scenarios, default=['ssp126'])
    
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
    


    @param.depends('variable', 'models', 'temporal_resolution', 'scenarios', 'color_scale_selector', watch=True)
    def update_plot(self):
        # Update the color palette based on the selected color scale
        self.update_color_palette()

        # Clear the figure and legend items
        self.figure.renderers = []
        self.figure.legend.items = []

        legend_items = []

        # Plot the constant dataset
        line = self.figure.line(self.constant_time, self.constant_values, legend_label="Osisaf", line_width=2, color="black")#, line_dash="dashed")
        legend_items.append(LegendItem(label="Osisaf", renderers=[line]))

        color_index = 0
        for model_index, model in enumerate(self.models):
            for scenario_index, scenario in enumerate(self.scenarios):
                try:
                    # Download and extract data
                    self.data_info = tk.download_and_extract_data(self.variable, model, self.temporal_resolution, scenario)
                    if self.data_info is None:
                        raise ValueError("Data could not be loaded.")
                    
                    da = self.data_info['da']
                    print(da)
                    time = da.time.values
                    print(time)
                    values = da.values
                    
                    # Get color for the model and scenario
                    scenario_color = self.color_palette[color_index % len(self.color_palette)]
                    color_index += 1
                    
                    line = self.figure.line(time, values, legend_label=f"{model} - {scenario}", line_width=2, color=scenario_color)
                    legend_items.append(LegendItem(label=f"{model} - {scenario}", renderers=[line]))

                    """
                    # Calculate percentiles and median
                    percentile_data = tk.calculate_percentiles_and_median(da)
                                                      
                    #print(f"day_of_year: {percentile_data['cds_percentile_2575']['day_of_year']}")
                    #print(f"percentile_25: {percentile_data['cds_percentile_2575']['percentile_25']}")
                    #print(f"percentile_75: {percentile_data['cds_percentile_2575']['percentile_75']}")


                    varea = self.figure.varea(x='day_of_year',
                                      y1='percentile_25',
                                      y2='percentile_75',
                                      source=percentile_data['cds_percentile_2575'],
                                      fill_alpha=0.6,
                                      fill_color='gray'  
                                      )
                                      
                    
                    legend_items.append(LegendItem(label=f"{model} - {scenario} (25-75 percentile)", renderers=[varea]))
                    """

                    """
                    # Calculate min/max 
                    min_max_data = tk.calculate_min_max(da)

                    min_line = self.figure.line(x='day_of_year',
                                                y='minimum',
                                                source=min_max_data['cds_minimum']
                    )

                    max_line = self.figure.line(x='day_of_year',
                                                y='maximum',
                                                source=min_max_data['cds_maximum']
                    )

                    legend_items.append(LegendItem(label=f"{model} - {scenario} minimum", renderers=[min_line]))
                    legend_items.append(LegendItem(label=f"{model} - {scenario} maximum", renderers=[max_line]))

                    """
                    #Monthly, seasonal, yearly resolution




                    
                    
                except Exception as e:
                    logging.error(f"An error occurred while processing {model} - {scenario}: {e}")
    
        # Create a new legend with the updated items
        self.figure.legend.items = legend_items
        self.figure.legend.title = "Legend"
        self.figure.legend.location = "bottom_left"
        self.figure.legend.click_policy = "hide"
        self.figure.legend.label_text_font_size = "10pt"
        self.figure.legend.background_fill_alpha = 0
    

    def view(self):
        # Create the widgets
        return pn.Row( 
            pn.Column(
            pn.Param(self.param, widgets={
                'color_scale_selector': pn.widgets.Select,
                'variable': pn.widgets.Select,
                'temporal_resolution': pn.widgets.Select,
                'models': pn.widgets.CheckBoxGroup,
                'scenarios': pn.widgets.CheckBoxGroup,
            }),
            ),
            self.figure
        )
    

sea_ice_analysis = SeaIceAnalysis()
pn.serve(sea_ice_analysis.view, title='Sea Ice Analysis')