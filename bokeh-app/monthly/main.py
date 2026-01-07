import os
import sys

# Get the root directory of the app 
app_root = os.getenv('APP_ROOT')
# Add the directory containing toolkit.py to the system path
sys.path.append(os.path.join(app_root, 'bokeh-app'))

import panel as pn
from bokeh.plotting import figure
from bokeh.io import show
from bokeh.models import HoverTool, Paragraph, LegendItem, Legend, DatetimeAxis, CustomJSHover, CustomJS, ColumnDataSource, Band, Button, VArea
import logging
import param
from bokeh.palettes import viridis, cividis, plasma, Category10
from bokeh.colors import RGB
from bokeh.transform import linear_cmap
import xarray as xr
import numpy as np 
import pandas as pd
from functools import lru_cache

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

@lru_cache(maxsize=128)  # Cache up to 128 unique datasets
def download_and_extract_data(var_type, model, temp_reso, scenario, ensemble_member='r1i1p1f1'):
    url_prefix = 'https://thredds.met.no/thredds/dodsC/metusers/steingod/deside/climmodseaice'
    modified_model = model[:-8]

    #url = f'{url_prefix}/{var_type}/{model}/{temp_reso}/{scenario}/{var_type}_SImon_{modified_model}_{scenario}_r1i1p1f1_2015_2100.nc'
    url = f'{url_prefix}/{var_type}/{model}/{temp_reso}/{scenario}/{ensemble_member}/{var_type}_SImon_{modified_model}_{scenario}_{ensemble_member}_2015_2100.nc'
    #download_and_extract_data('siarean', 'NorESM2-LM_sea_ice', 'Monthly', 'ssp126')
    try:
        ds = xr.open_dataset(url, cache=False)
        da = ds[var_type]
        title = ds.title
        long_name = da.attrs['long_name']
        units = da.attrs['units']
        return {"da": da, "title": title, "long_name": long_name, "units": units}
    except Exception as e:
        print("An error occurred:", e)
        return None


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

# Create a mapping dictionary for displaying variables 
variable_mapping = {
    'Sea Ice Area': 'siarean',
    'Sea Ice Extent': 'siextentn'
} 

class SeaIceAnalysis(param.Parameterized):
    color_scale_selector = param.Selector(objects=list(color_groups['Sequential color maps'].keys()) + list(color_groups['Non-sequential color maps'].keys()), default='Viridis')
    variable = param.Selector(objects=list(variable_mapping.keys()), default='Sea Ice Area')
    temporal_resolution = param.Selector(objects=['Seasonal'], default='Seasonal')
    models = param.ListSelector(objects=[
        'NorESM2-LM_sea_ice', 
        'MRI-ESM2-0_sea_ice', 
        'MIROC6_sea_ice', 
        'EC-Earth3-Veg_sea_ice', 
        'CanESM5_sea_ice', 
        'ACCESS-CM2_sea_ice'], 
        default=['MRI-ESM2-0_sea_ice'])
    scenarios = param.ListSelector(objects=ssp_scenarios, default=['ssp126'])

    # Adding ensemble members
    ensemble_members = param.ListSelector(
        objects=['r1i1p1f1', 'r2i1p1f1', 'r3i1p1f1', 'r4i1p1f1', 'r5i1p1f1', 'r6i1p1f1', 'r7i1p1f1', 'r8i1p1f1', 'r9i1p1f1', 'r10i1p1f1'], 
        default=['r1i1p1f1']
    )
    
    # Add selection of months when selecting Seasonal reso
    season_months = param.ListSelector(objects=['DJF','MAM','JJA','SON'], default=['DJF'])

    # Adding statistics selector
    show_band = param.Boolean(default=False)  # Parameter to toggle the band visibility
    _band_renderers = [] # Track band renderes added to the figure
    _band = None


    def __init__(self, **params):
        super().__init__(**params)

        # Load OSISAF data once during initialization
        self.constant_dataset = xr.open_dataset('https://thredds.met.no/thredds/dodsC/osisaf/met.no/ice/index/v2p3/nh/osisaf_nh_sia_monthly.nc')
        self.constant_time = pd.to_datetime(self.constant_dataset.time.values)
        self.constant_values = self.constant_dataset['sia'].values

        self.data_info = None
        self.figure = figure(title="Sea Ice Visualization", x_axis_label='Year', y_axis_label='1e6 km2', x_axis_type='datetime')#, width=1500, height=800)
        self.figure.title.text_font_size = "20pt"
        self.figure.ygrid.grid_line_color = 'black'
        self.figure.xgrid.grid_line_color = 'black'
        self.figure.xaxis.axis_label_text_font_size = "20pt"
        self.figure.yaxis.axis_label_text_font_size = "20pt"
        self.figure.ygrid.grid_line_alpha = 0.2
        self.figure.xgrid.grid_line_alpha = 0.2
        self.figure.sizing_mode = 'stretch_both' 

        # Create buttons
        self.model_info_button = pn.widgets.Button(name='Model Information', button_type='success')
        self.scenario_info_button = pn.widgets.Button(name='Scenario Information', button_type='success')
        self.variable_info_button = pn.widgets.Button(name='Variable Information', button_type='success')

        # Add a toggle button for showing/hiding the band
        self.band_toggle_button = pn.widgets.Toggle(name='Show Spread Band', button_type="primary", value=self.show_band)
        self.band_toggle_button.param.watch(self.toggle_band_visibility, 'value')
        
        self.season_months_widget = pn.Param(self.param.season_months, widgets={'season_months': pn.widgets.CheckBoxGroup})

        self.update_season_selector_visibility()
        self.update_plot() # Initialize the plot with default parameters


    def toggle_band_visibility(self, event):
        """
        #Updates the 'show_band' parameter and triggers a re-render of the plot
        #when the toggle button is clicked.
        """
        self.show_band = event.new  # Update the show_band parameter
        self.update_plot()  # Re-render the plot 


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
    
    
    @param.depends('variable', 'models', 'scenarios', 'ensemble_members', 'color_scale_selector', 'season_months', 'show_band', watch=True)
    def update_plot(self):
        # Update the color palette based on the selected color scale
        self.update_color_palette()

        # Clear the figure and legend items
        self.figure.renderers = []
        self.figure.legend.items = []

        # Remove bands and mean line if they exist in _band_renderers
        if self._band_renderers:
            print('Removing Bands and Mean Line...')
            for renderer in self._band_renderers[:]:  # Use a copy of the list to avoid modifying it during iteration
                try:
                    if renderer in self.figure.center:  
                        self.figure.center.remove(renderer) 
                        print(f"Removed renderer: {renderer}")
                    else:
                        print(f"Renderer already removed: {renderer}")
                except (AttributeError, ValueError) as e:
                    print(f"Error removing renderer: {e}")
            self._band_renderers.clear()  # Clear the list after removal
            print('Tracked Bands After Removal:', self._band_renderers)
        
        legend_items = []
        added_osisaf_legends = set()

        # Get the actual variable name from the mapping
        actual_variable = variable_mapping[self.variable]

        # Remove OSISAF data from the original line plot
        line = self.figure.line(self.constant_time, self.constant_values, legend_label="Osisaf", line_width=2, color="black")
        line.visible = False
        
        color_index = 0
        for model_index, model in enumerate(self.models):
            for scenario_index, scenario in enumerate(self.scenarios):
                for ensemble_member in self.ensemble_members: 
                    # Use the actual variable name for data extraction
                    self.data_info = download_and_extract_data(actual_variable, model, 'Monthly', scenario, ensemble_member)  
                    
                    if self.data_info is None:
                        raise ValueError(f"Data could not be loaded ({model[0:10]} {scenario} {ensemble_member}).")

                    # Get color for the model and scenario
                    scenario_color = self.color_palette[color_index % len(self.color_palette)]
                    color_index += 1

                    # Set xr.DataArray
                    da = self.data_info['da']

                    # Define season-to-month mapping and line styles for plotting
                    season_to_months = {
                        #'DJF': [12, 1, 2],
                        'DJF': [12, 1, 2,3,4,5,6,7,8,9,10,11],
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

                        
                        osi_name = 'OSISAF'
                        source_osi = ColumnDataSource(data={
                            'date': osi_season_dates,
                            'value': osi_season_values,
                            'model': [osi_name] * len(osi_season_dates)  # Repeat 'OSISAF' for each date
                        })

                        # Define the hover tool with tooltips
                        TOOLTIPS = '''
                            <div>
                                <div>
                                    <span style="font-size: 12px; font-weight: bold">Model:</span>
                                    <span style="font-size: 12px;">@model</span>
                                </div>
                                <div>
                                    <span style="font-size: 12px; font-weight: bold">Date:</span>
                                    <span style="font-size: 12px;">@date{%F}</span>
                                </div>
                                <div>
                                    <span style="font-size: 12px; font-weight: bold">Value:</span>
                                    <span style="font-size: 12px;">@value{0.000}</span>
                                    <span style="font-size: 12px;">mill. km<sup>2</sup></span>
                                </div>
                            </div>
                        '''

                        # Add HoverTool to the figure
                        hover_tool = HoverTool(tooltips=TOOLTIPS, formatters={'@date': 'datetime'}, visible=False)
                        self.figure.add_tools(hover_tool)

                        # Plot the seasonal OSISAF data (only add legend once)
                        if f'Seasonal OSISAF {season}' not in added_osisaf_legends:
                            osi_point = self.figure.line('date','value', source=source_osi, legend_label=f'OSISAF', line_width=3, color='black', line_dash=line_dash)
                            legend_items.append(LegendItem(label=f'OSISAF {season}', renderers=[osi_point]))
                            added_osisaf_legends.add(f'Seasonal OSISAF')
                        
                        
                        line_width = 2 if not self.show_band else 0.1  
                        # Define the path to the precomputed .nc file
                        nc_file_path = f"https://thredds.met.no/thredds/dodsC/metusers/steingod/deside/climmodseaice/EnsambleSpread4Visualization/{model}_{scenario}_statistics.nc"
                        
                        # Load the .nc file
                        ds = xr.open_dataset(nc_file_path)

                        # Extract data from the .nc file
                        nc_years = ds['year'].values
                        mean_values = ds['mean'].values
                        min_values = ds['min'].values
                        max_values = ds['max'].values
                        std_values = ds['std'].values

                        # Prepare the dates for plotting
                        season_dates = [pd.Timestamp(year=int(year), month=1, day=1) for year in nc_years]

                        # Extract the part of the model name before the first underscore
                        model_name = model.split('_')[0]    

                        # Add the mean line to the figure
                        print('Adding Mean Line...')
                        mean_line_source = ColumnDataSource(data={
                            'date': season_dates,
                            'value': mean_values,
                            'model': [f'{model} - {scenario} Mean'] * len(season_dates)
                        })

                        mean_line = self.figure.line(
                            'date', 'value', source=mean_line_source,
                            legend_label=f'{model} - {scenario} Mean',
                            line_width=5, color=scenario_color, line_dash='dashed' #powderblue
                        )

                        # Add a hover tool for the mean line
                        mean_hover_tool = HoverTool(
                            renderers=[mean_line],
                            tooltips='''
                                <div>
                                    <div>
                                        <span style="font-size: 12px; font-weight: bold">Model:</span>
                                        <span style="font-size: 12px;">@model</span>
                                    </div>
                                    <div>
                                        <span style="font-size: 12px; font-weight: bold">Date:</span>
                                        <span style="font-size: 12px;">@date{%F}</span>
                                    </div>
                                    <div>
                                        <span style="font-size: 12px; font-weight: bold">Mean Value:</span>
                                        <span style="font-size: 12px;">@value{0.000}</span>
                                        <span style="font-size: 12px;">mill. km<sup>2</sup></span>
                                    </div>
                                </div>
                            ''',
                            formatters={'@date': 'datetime'},
                            mode='vline'
                        )
                        self.figure.add_tools(mean_hover_tool)
                        legend_items.append(LegendItem(label=f'Mean {model_name} {scenario}', renderers=[mean_line]))

                        # Create a ColumnDataSource for the spread band
                        spread_source = ColumnDataSource(data={
                            'date': season_dates,
                            'lower': min_values,
                            'upper': max_values
                        })
                        
                        # Add the spread band to the figure
                        print('Adding Spread Band...')                       
                        spread_band = Band(
                            base='date', lower='lower', upper='upper', source=spread_source,
                            fill_alpha=0.1,
                            fill_color=scenario_color,
                            line_color='black',
                            line_width=1
                        )
                        
                        self.figure.add_layout(spread_band)  
                        self._band_renderers.append(spread_band) 
                        print('Tracked Bands:', self._band_renderers)

                        # Add a dummy line for the legend
                        dummy_line_spread = self.figure.line(
                            [], [],  # Empty data
                            line_width=1, color=scenario_color
                        )
                        legend_items.append(LegendItem(label=f'Spread {model_name} {scenario} (light)', renderers=[dummy_line_spread]))
                        


                        # Add the standard deviation band (around the mean)
                        std_source = ColumnDataSource(data={
                            'date': season_dates,
                            'lower': mean_values - std_values,
                            'upper': mean_values + std_values
                        })

                        std_band = Band(
                            base='date', lower='lower', upper='upper', source=std_source,
                            fill_alpha=0.5,  
                            fill_color=scenario_color,#'teal',  
                            line_color=None  
                        )
                        self.figure.add_layout(std_band)  
                        self._band_renderers.append(std_band)
                        print('Tracked Bands (with Std):', self._band_renderers)

                        # Add a dummy line for the legend
                        dummy_line_std = self.figure.line(
                            [], [],  # Empty data
                            line_width=1, color=scenario_color
                        )
                        legend_items.append(LegendItem(label=f'std {model_name} {scenario} (dark)', renderers=[dummy_line_std]))
             
                        
        # Create a new legend with the updated items
        if self.figure.renderers:
            self.figure.legend.items = legend_items
            self.figure.legend.title = "Legend"
            self.figure.legend.title_text_font_size = "20pt" 
            self.figure.legend.location = "bottom_left"
            self.figure.legend.click_policy = "hide"
            self.figure.legend.label_text_font_size = "15pt"
            self.figure.legend.background_fill_alpha = 0

            self.figure.yaxis.axis_label = f'{self.variable} [million km²]'

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
        model_tooltips = {
            'NorESM2-LM_sea_ice': "NorESM2-LM: Focuses on climate interactions and ocean circulation. See: https://gmd.copernicus.org/articles/13/6165/2020/",
            'MRI-ESM2-0_sea_ice': "MRI-ESM2-0: Emphasizes atmospheric processes and variability. See: https://www.wdc-climate.de/ui/cmip6?input=CMIP6.CMIP.MRI.MRI-ESM2-0",
            'MIROC6_sea_ice': "MIROC6: Detailed atmospheric and oceanic simulations. See: https://gmd.copernicus.org/articles/12/2727/2019/",
            'EC-Earth3-Veg_sea_ice': "EC-Earth3-Veg: Integrates dynamic vegetation processes. See: https://gmd.copernicus.org/articles/15/2973/2022/",
            'CanESM5_sea_ice': "CanESM5: Includes advanced carbon cycle interactions. See: https://gmd.copernicus.org/articles/12/4823/2019/",
            'ACCESS-CM2_sea_ice': "ACCESS-CM2: Highlights regional climate dynamics. See: https://www.access-nri.org.au/models/earth-system-models/coupled-model-cm/"
        }

        scenario_tooltips = {
            'ssp126': 'ssp126: Low emissions scenario, focusing on sustainability and reduced reliance on fossil fuels.',
            'ssp245': 'ssp245: Intermediate emissions scenario, balancing economic growth with moderate climate policies.',
            'ssp370': 'ssp370: High emissions scenario, characterized by regional rivalry and limited climate action.',
            'ssp460': 'ssp460: Intermediate emissions scenario with delayed, but eventual, emissions reductions.',
            'ssp585': 'ssp585: Very high emissions scenario, driven by fossil fuel development and minimal climate policies.',
            'See:': 'See: https://www.anthesisgroup.com/insights/five-future-scenarios-ar6-ipcc/' 
        }

        season_tooltips = {
            'DJF': 'DJF: December, January, February',
            'MAM': 'MAM: March, April, May',
            'JJA': 'JJA: June, July, August',
            'SON': 'SON: September, October, November'
        }

        # Wrap CheckBoxGroup in Tooltip
        model_tooltip = pn.widgets.TooltipIcon(value="\n\n".join([f"{tooltip}" for model, tooltip in model_tooltips.items()])) 
        scenario_tooltip = pn.widgets.TooltipIcon(value="\n\n".join([f"{tooltip}" for model, tooltip in scenario_tooltips.items()])) 
        season_tooltip = pn.widgets.TooltipIcon(value="\n\n".join([f"{tooltip}" for model, tooltip in season_tooltips.items()])) 
        
        # Add the widgets and the figure to the layout
        widget_layout = pn.Column(
            pn.pane.Markdown("### Color Scale Selector"),
            pn.Param(self.param.color_scale_selector, widgets={'color_scale_selector': pn.widgets.Select}),
            pn.pane.Markdown("### Variable"),
            pn.Param(self.param.variable, widgets={'variable': pn.widgets.Select}),
            #variable_info,
            pn.pane.Markdown("### Temporal Resolution"),
            pn.Param(self.param.temporal_resolution, widgets={'temporal_resolution': pn.widgets.Select}),
            pn.pane.Markdown("### Models"),
            pn.Param(self.param.models, widgets={'models': pn.widgets.CheckBoxGroup}),
            model_tooltip,
            pn.pane.Markdown("### Scenarios"),
            pn.Param(self.param.scenarios, widgets={'scenarios': pn.widgets.CheckBoxGroup}),
            scenario_tooltip,
            #pn.pane.Markdown("### Season Selector"),
            #pn.Param(self.param.season_months, widgets={'season_months': pn.widgets.CheckBoxGroup}),
            #season_tooltip,    
        )

        return pn.Row(widget_layout, self.figure)
        
sea_ice_analysis = SeaIceAnalysis()
sea_ice_analysis.view().servable(title='Sea Ice Analysis')
