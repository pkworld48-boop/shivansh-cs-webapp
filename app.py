import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import MultipleLocator
from shapely.geometry import LineString, Polygon
import io
import zipfile
import numpy as np

# ================= PAGE SETUP & CSS =================
st.set_page_config(page_title="Shiv Ansh Infra CS Engine (Pro)", layout="wide", initial_sidebar_state="expanded")

custom_css = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stToolbar"] {visibility: hidden !important;}
[data-testid="stHeaderActionElements"] {visibility: hidden !important;}
.viewerBadge_container {display: none !important;}
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

if 'ogl_df' not in st.session_state:
    st.session_state.ogl_df = pd.DataFrame()
if 'frl_dict' not in st.session_state:
    st.session_state.frl_dict = {}

st.title("Shiv Ansh Infra Earthwork CS Engine (Pro V5.3)")

# ================= CORE FUNCTIONS =================
def calculate_toe_points(ogl_line, edge_x, edge_y, slope_ratio, is_left, max_toe):
    if slope_ratio == 0:
        vert_line = LineString([(edge_x, edge_y + 100), (edge_x, edge_y - 100)])
        inter = vert_line.intersection(ogl_line)
        ogl_y = inter.y if (not inter.is_empty and inter.geom_type == 'Point') else edge_y - 3
        return [(edge_x, ogl_y), (edge_x, edge_y)] if is_left else [(edge_x, edge_y), (edge_x, ogl_y)]
    
    vert_edge = LineString([(edge_x, edge_y + 100), (edge_x, edge_y - 100)])
    edge_inter = vert_edge.intersection(ogl_line)
    
    if not edge_inter.is_empty:
        ogl_y_at_edge = edge_inter.y if edge_inter.geom_type == 'Point' else (edge_inter.geoms[0].y if edge_inter.geom_type == 'MultiPoint' else edge_y - 1)
    else:
        ogl_y_at_edge = edge_y - 1
        
    is_fill = edge_y >= ogl_y_at_edge
    direction = -1 if is_left else 1
    ext_x = edge_x + direction * 200
    drop = 200 / slope_ratio
    slope_line = LineString([(edge_x, edge_y), (ext_x, edge_y - drop)]) if is_fill else LineString([(edge_x, edge_y), (ext_x, edge_y + drop)])
    
    inter = slope_line.intersection(ogl_line)
    int_x, int_y = None, None
    
    if not inter.is_empty:
        if inter.geom_type == 'Point':
            int_x, int_y = inter.x, inter.y
        elif inter.geom_type == 'MultiPoint':
            pts = list(inter.geoms)
            pts.sort(key=lambda p: abs(p.x - edge_x))
            int_x, int_y = pts[0].x, pts[0].y
            
    exceeds_limit = True if int_x is None else (is_left and int_x < max_toe) or (not is_left and int_x > max_toe)
    
    if exceeds_limit:
        dist = abs(max_toe - edge_x)
        slope_y_at_wall = edge_y - (dist / slope_ratio) if is_fill else edge_y + (dist / slope_ratio)
        vert = LineString([(max_toe, edge_y + 100), (max_toe, edge_y - 100)])
        v_inter = vert.intersection(ogl_line)
        ogl_y_at_wall = v_inter.y if (not v_inter.is_empty and v_inter.geom_type == 'Point') else slope_y_at_wall - 2
        return [(max_toe, ogl_y_at_wall), (max_toe, slope_y_at_wall)] if is_left else [(max_toe, slope_y_at_wall), (max_toe, ogl_y_at_wall)]
        
    return [(int_x, int_y)]

# ================= SIDEBAR UI =================
st.sidebar.header("📁 File Uploads")

ogl_sample = "Chainage,Offset,Elevation\n10,-15,98.500\n10,-10,98.600\n10,-5,98.700\n10,0,98.800\n10,5,98.700\n10,10,98.600\n10,15,98.500\n20,-15,99.100\n20,-10,99.200\n20,-5,99.400\n20,0,99.500\n20,5,99.300\n20,10,99.200\n20,15,99.100"
frl_sample = "Chainage,FRL\n10,99.500\n20,100.200"

st.sidebar.markdown("<span style='font-size:12px; color:gray;'>Download Sample Formats:</span>", unsafe_allow_html=True)
col_samp1, col_samp2 = st.sidebar.columns(2)
with col_samp1:
    st.download_button(label="📄 OGL Template", data=ogl_sample, file_name="Sample_OGL.csv", mime="text/csv", use_container_width=True)
with col_samp2:
    st.download_button(label="📄 FRL Template", data=frl_sample, file_name="Sample_FRL.csv", mime="text/csv", use_container_width=True)

st.sidebar.markdown("---")

ogl_file = st.sidebar.file_uploader("Upload OGL CSV", type=['csv'])
frl_file = st.sidebar.file_uploader("Upload FRL CSV (Optional)", type=['csv'])

if ogl_file:
    df = pd.read_csv(ogl_file)
    df['Chainage'] = df['Chainage'].apply(lambda x: f"{float(x):g}" if pd.notnull(x) else str(x))
    st.session_state.ogl_df = df

if frl_file:
    df_f = pd.read_csv(frl_file)
    st.session_state.frl_dict = {f"{float(row['Chainage']):g}": float(row['FRL']) for _, row in df_f.iterrows() if pd.notnull(row['Chainage'])}
else:
    if frl_file is None and not st.session_state.frl_dict:
        st.session_state.frl_dict = {}

st.sidebar.header("📝 Project Details")
show_branding = st.sidebar.checkbox("☑ Show Company Branding", value=True)
dept_name = st.sidebar.text_input("Department Name", "Public Works Department (PWD)")
work_name = st.sidebar.text_input("Name of Work", "Construction of Road Project")

st.sidebar.header("⚙️ Parameters")
title_prefix = st.sidebar.text_input("Plot Title Prefix", "Cross Section at CH: ")

st.sidebar.markdown("**Carriageway Camber (%)**")
cw_cam_col1, cw_cam_col2 = st.sidebar.columns(2)
with cw_cam_col1:
    l_cw_camber = st.number_input("Left CW Camber (%)", value=2.50, format="%.2f")
with cw_cam_col2:
    r_cw_camber = st.number_input("Right CW Camber (%)", value=2.50, format="%.2f")

st.sidebar.markdown("**Shoulder Camber (%)**")
sh_cam_col1, sh_cam_col2 = st.sidebar.columns(2)
with sh_cam_col1:
    l_sh_camber = st.number_input("Left Shldr Camber (%)", value=4.00, format="%.2f")
with sh_cam_col2:
    r_sh_camber = st.number_input("Right Shldr Camber (%)", value=4.00, format="%.2f")

st.sidebar.markdown("**Pavement Crust Layers**")
include_crust = st.sidebar.checkbox("☑ Include Crust Layers", value=True)
crust_thk = {'bc': 0.0, 'dbm': 0.0, 'wmm': 0.0, 'gsb': 0.0, 'subgrade': 0.0}
crust_slope = 0.0

if include_crust:
    crust_slope = st.sidebar.number_input("Crust Side Slope (H:1)", value=1.0, format="%.2f")
    cr_c1, cr_c2 = st.sidebar.columns(2)
    with cr_c1:
        crust_thk['bc'] = st.number_input("BC (mm)", value=40.0)
        crust_thk['wmm'] = st.number_input("WMM (mm)", value=250.0)
        crust_thk['subgrade'] = st.number_input("Subgrade (mm)", value=500.0)
    with cr_c2:
        crust_thk['dbm'] = st.number_input("DBM (mm)", value=75.0)
        crust_thk['gsb'] = st.number_input("GSB (mm)", value=230.0)

st.sidebar.markdown("**Carriageway & Shoulders**")
col1, col2 = st.sidebar.columns(2)
with col1:
    st.markdown("**LEFT SIDE**")
    l_cw = abs(st.number_input("L-Carriageway", value=3.50))
    l_sh = abs(st.number_input("L-Shoulder", value=1.50))
    l_slope = st.number_input("L-Toe Slope (H:1)", value=2.0)
    max_l_toe = -abs(st.number_input("Max L-Toe", value=30.0))
with col2:
    st.markdown("**RIGHT SIDE**")
    r_cw = abs(st.number_input("R-Carriageway", value=3.50))
    r_sh = abs(st.number_input("R-Shoulder", value=1.50))
    r_slope = st.number_input("R-Toe Slope (H:1)", value=2.0)
    max_r_toe = abs(st.number_input("Max R-Toe", value=30.0))

# ================= MAIN AREA =================
if not st.session_state.ogl_df.empty:
    chainages = st.session_state.ogl_df['Chainage'].unique()
    
    col_sel, col_msg, col_btn = st.columns([2, 3, 5])
    with col_sel:
        ch_sel = st.selectbox("Select Chainage", chainages)
        
    frl_val = st.session_state.frl_dict.get(ch_sel, None)
    has_frl = frl_val is not None
    
    with col_msg:
        st.write("") 
        if has_frl:
            st.success(f"Active FRL: {frl_val} m")
        else:
            st.warning("FRL Missing: Showing OGL Only")
            
    with col_btn:
        st.write("") 
        view_mode = st.radio("View Mode", ["Cross Section", "L-Section"], horizontal=True, label_visibility="collapsed")

    def get_elev(line, target_x):
        vert = LineString([(target_x, -1000), (target_x, 1000)])
        inter = line.intersection(vert)
        if not inter.is_empty:
            if inter.geom_type == 'Point':
                return f"{inter.y:.3f}"
            elif inter.geom_type == 'MultiPoint':
                return f"{inter.geoms[0].y:.3f}"
            elif inter.geom_type == 'LineString':
                return f"{list(inter.coords)[0][1]:.3f}"
            else:
                return f"{inter.bounds[1]:.3f}"
                
        min_x, min_y, max_x, max_y = line.bounds
        if abs(target_x - min_x) <= 0.005:
            return f"{next((p[1] for p in line.coords if p[0] == min_x), line.coords[0][1]):.3f}"
        if abs(target_x - max_x) <= 0.005:
            return f"{next((p[1] for p in line.coords if p[0] == max_x), line.coords[-1][1]):.3f}"
        return "-"

    def get_geometry(ogl_line, frl_v):
        l_cw_x = -l_cw
        l_cw_y = frl_v - l_cw * (l_cw_camber / 100.0)
        r_cw_x = r_cw
        r_cw_y = frl_v - r_cw * (r_cw_camber / 100.0)
        
        l_sh_x = -(l_cw + l_sh)
        l_sh_y = l_cw_y - l_sh * (l_sh_camber / 100.0)
        r_sh_x = (r_cw + r_sh)
        r_sh_y = r_cw_y - r_sh * (r_sh_camber / 100.0)
        
        total_crust_m = sum(crust_thk.values()) / 1000.0 if include_crust else 0.0
        
        if include_crust:
            l_crust_bot_x = l_cw_x - total_crust_m * crust_slope
            l_crust_bot_y = l_cw_y - total_crust_m
            r_crust_bot_x = r_cw_x + total_crust_m * crust_slope
            r_crust_bot_y = r_cw_y - total_crust_m
            c_crust_bot_y = frl_v - total_crust_m
            
            dy_l = max(0, l_sh_y - l_crust_bot_y)
            outer_l_x = min(l_sh_x - dy_l * l_slope, l_crust_bot_x)
            outer_l_y = l_crust_bot_y
            
            dy_r = max(0, r_sh_y - r_crust_bot_y)
            outer_r_x = max(r_sh_x + dy_r * r_slope, r_crust_bot_x)
            outer_r_y = r_crust_bot_y
            
            core_pts = []
            if outer_l_x < l_crust_bot_x: core_pts.append((outer_l_x, outer_l_y))
            core_pts.append((l_crust_bot_x, l_crust_bot_y))
            core_pts.append((0, c_crust_bot_y))
            core_pts.append((r_crust_bot_x, r_crust_bot_y))
            if outer_r_x > r_crust_bot_x: core_pts.append((outer_r_x, outer_r_y))
        else:
            core_pts = [(l_sh_x, l_sh_y), (0, frl_v), (r_sh_x, r_sh_y)]
            outer_l_x, outer_l_y = l_sh_x, l_sh_y
            outer_r_x, outer_r_y = r_sh_x, r_sh_y

        prop_pts = calculate_toe_points(ogl_line, outer_l_x, outer_l_y, l_slope, True, max_l_toe) + \
                   core_pts + \
                   calculate_toe_points(ogl_line, outer_r_x, outer_r_y, r_slope, False, max_r_toe)
                   
        return prop_pts, l_cw_x, l_cw_y, r_cw_x, r_cw_y, l_sh_x, l_sh_y, r_sh_x, r_sh_y, outer_l_x, outer_l_y, outer_r_x, outer_r_y

    def draw_cs(current_ch):
        ch_df = st.session_state.ogl_df[st.session_state.ogl_df['Chainage'] == current_ch].copy()
        if ch_df.empty:
            return None
            
        is_frl_present = current_ch in st.session_state.frl_dict
        
        ogl_points = sorted(list(zip(ch_df['Offset'].tolist(), ch_df['Elevation'].tolist())), key=lambda pt: pt[0])
        ogl_line = LineString([(-500, ogl_points[0][1])] + ogl_points + [(500, ogl_points[-1][1])])
        
        plot_ogl_x = [pt[0] for pt in ogl_points]
        plot_ogl_y = [pt[1] for pt in ogl_points]
        
        if is_frl_present:
            frl_v = st.session_state.frl_dict[current_ch]
            prop_pts, l_cw_x, l_cw_y, r_cw_x, r_cw_y, l_sh_x, l_sh_y, r_sh_x, r_sh_y, outer_l_x, outer_l_y, outer_r_x, outer_r_y = get_geometry(ogl_line, frl_v)
            prop_x, prop_y = [p[0] for p in prop_pts], [p[1] for p in prop_pts]
            prop_line = LineString(prop_pts)
            
            if min(prop_x) < plot_ogl_x[0]:
                plot_ogl_x.insert(0, min(prop_x)); plot_ogl_y.insert(0, plot_ogl_y[0])
            if max(prop_x) > plot_ogl_x[-1]:
                plot_ogl_x.append(max(prop_x)); plot_ogl_y.append(plot_ogl_y[-1])
            
        fig, ax = plt.subplots(figsize=(11, 7.8))
        fig.subplots_adjust(left=0.300, bottom=0.55, right=0.95, top=0.82) 
        
        if show_branding:
            fig.text(0.05, 0.95, "SHIV ANSH INFRA", fontsize=16, fontweight='bold', color='navy')
            fig.text(0.05, 0.91, "DGPS Survey & Infra Solutions", fontsize=10, fontstyle='italic', color='dimgray')
        
        fig.text(0.65, 0.96, dept_name, fontsize=14, fontweight='bold', ha='center', color='black')
        fig.text(0.65, 0.92, work_name, fontsize=11, ha='center', color='dimgray')

        ax.plot(plot_ogl_x, plot_ogl_y, marker='o', color='green', label='OGL', linewidth=2)
        
        layers_legend_handles = []
        
        if is_frl_present:
            ax.plot(prop_x, prop_y, marker='s', color='blue', label='Earthwork / Formation Line', linewidth=2, linestyle='--' if include_crust else '-')
            
            if include_crust:
                ax.plot([l_cw_x, 0, r_cw_x], [l_cw_y, frl_v, r_cw_y], color='navy', linewidth=2.5, label='Paved Top Surface')
                if l_sh_x < l_cw_x:
                    ax.plot([l_sh_x, l_cw_x], [l_sh_y, l_cw_y], color='saddlebrown', linewidth=1.5)
                if r_sh_x > r_cw_x:
                    ax.plot([r_cw_x, r_sh_x], [r_cw_y, r_sh_y], color='saddlebrown', linewidth=1.5)
            else:
                ax.plot([l_sh_x, l_cw_x, 0, r_cw_x, r_sh_x], [l_sh_y, l_cw_y, frl_v, r_cw_y, r_sh_y], color='navy', linewidth=2.5, label='Top Surface')
                
            ax.plot([0], [frl_v], marker='*', color='red', markersize=10, label=f'FRL ({frl_v}m)')

            if include_crust and sum(crust_thk.values()) > 0:
                y_curr_c, y_curr_l, y_curr_r = frl_v, l_cw_y, r_cw_y
                x_curr_l, x_curr_r = l_cw_x, r_cw_x
                
                layers = [
                    ('BC', crust_thk['bc']/1000.0, 'black', 0.8, ''),
                    ('DBM', crust_thk['dbm']/1000.0, 'dimgray', 0.9, ''),
                    ('WMM', crust_thk['wmm']/1000.0, 'orange', 0.6, '...'),
                    ('GSB', crust_thk['gsb']/1000.0, 'gold', 0.5, 'oo'),
                    ('Subgrade', crust_thk['subgrade']/1000.0, 'saddlebrown', 0.3, 'xx')
                ]
                
                for name, thk, col, alp, htc in layers:
                    if thk > 0:
                        y_next_c = y_curr_c - thk
                        y_next_l = y_curr_l - thk
                        y_next_r = y_curr_r - thk
                        x_next_l = x_curr_l - thk * crust_slope
                        x_next_r = x_curr_r + thk * crust_slope
                        
                        poly_x = [x_curr_l, 0, x_curr_r, x_next_r, 0, x_next_l]
                        poly_y = [y_curr_l, y_curr_c, y_curr_r, y_next_r, y_next_c, y_next_l]
                        ax.fill(poly_x, poly_y, color=col, alpha=alp, hatch=htc, edgecolor='black', linewidth=0.5)
                        
                        y_curr_c, y_curr_l, y_curr_r = y_next_c, y_next_l, y_next_r
                        x_curr_l, x_curr_r = x_next_l, x_next_r
                        
                        patch = mpatches.Patch(facecolor=col, alpha=alp, hatch=htc, edgecolor='black', label=f"{name} Layer ({thk*1000:g}mm)")
                        layers_legend_handles.append(patch)
                
                if outer_l_x < x_curr_l:
                    poly_left_sh_x = [l_sh_x, l_cw_x, x_curr_l, outer_l_x]
                    poly_left_sh_y = [l_sh_y, l_cw_y, outer_l_y, outer_l_y]
                    ax.fill(poly_left_sh_x, poly_left_sh_y, color='saddlebrown', alpha=0.3, hatch='xx', edgecolor='black', linewidth=0.8)
                    ax.plot([l_sh_x, outer_l_x], [l_sh_y, outer_l_y], color='saddlebrown', linestyle='-', linewidth=1.5)
                
                if outer_r_x > x_curr_r:
                    poly_right_sh_x = [r_sh_x, r_cw_x, x_curr_r, outer_r_x]
                    poly_right_sh_y = [r_sh_y, r_cw_y, outer_r_y, outer_r_y]
                    ax.fill(poly_right_sh_x, poly_right_sh_y, color='saddlebrown', alpha=0.3, hatch='xx', edgecolor='black', linewidth=0.8)
                    ax.plot([r_sh_x, outer_r_x], [r_sh_y, outer_r_y], color='saddlebrown', linestyle='-', linewidth=1.5)
                
                es_patch = mpatches.Patch(facecolor='saddlebrown', alpha=0.3, hatch='xx', edgecolor='black', label="Earthen Shoulder")
                layers_legend_handles.append(es_patch)

            try:
                ogl_y_center = float(get_elev(ogl_line, 0))
                ax.vlines(x=0, ymin=ogl_y_center, ymax=frl_v, color='red', linestyle=':')
            except:
                pass
            
            cut_area, fill_area = 0.0, 0.0
            try:
                datum_y = min([y for x, y in ogl_points] + [y for x, y in prop_pts]) - 10
                prop_poly = Polygon(prop_pts + [(prop_pts[-1][0], datum_y), (prop_pts[0][0], datum_y)])
                ogl_poly = Polygon([prop_pts[0]] + [(x, y) for x, y in ogl_points if prop_pts[0][0] < x < prop_pts[-1][0]] + [prop_pts[-1], (prop_pts[-1][0], datum_y), (prop_pts[0][0], datum_y)])
                cut_area = ogl_poly.difference(prop_poly).area
                fill_area = prop_poly.difference(ogl_poly).area
                
                qty_text = f"Earthwork Cut = {cut_area:.3f} sq.m\nEarthwork Fill = {fill_area:.3f} sq.m"
                ax.text(0.02, 0.98, qty_text, transform=ax.transAxes, fontsize=9, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
            except:
                pass

            sorted_x = sorted(list(set([round(x, 3) for x in prop_x] + [round(x, 3) for x in plot_ogl_x])))
            
            full_top_pts = calculate_toe_points(ogl_line, l_sh_x, l_sh_y, l_slope, True, max_l_toe) + \
                           [(l_sh_x, l_sh_y), (l_cw_x, l_cw_y), (0, frl_v), (r_cw_x, r_cw_y), (r_sh_x, r_sh_y)] + \
                           calculate_toe_points(ogl_line, r_sh_x, r_sh_y, r_slope, False, max_r_toe)
            full_top_line = LineString(full_top_pts)
            
            table_elevs = [get_elev(full_top_line, x) for x in sorted_x]
            hatch_elevs = [get_elev(prop_line, x) for x in sorted_x]
            
        else: # FRL Missing
            sorted_x = sorted(list(set([round(x, 3) for x in plot_ogl_x])))
            table_elevs = ["-" for _ in sorted_x]
            hatch_elevs = ["-" for _ in sorted_x]
            
        cell_text = [table_elevs, [get_elev(ogl_line, x) for x in sorted_x], [f"{x:.3f}" for x in sorted_x]]
        
        if is_frl_present:
            try:
                nan = float('nan')
                y_p = [float(y) if y != "-" else nan for y in hatch_elevs]
                y_o = [float(y) if y != "-" else nan for y in cell_text[1]]
                
                ax.fill_between(sorted_x, y_o, y_p, where=[p >= o for p, o in zip(y_p, y_o)], interpolate=True, facecolor='maroon', edgecolor='maroon', alpha=0.3, hatch='///', label='EW Fill')
                ax.fill_between(sorted_x, y_o, y_p, where=[p < o for p, o in zip(y_p, y_o)], interpolate=True, facecolor='blue', edgecolor='blue', alpha=0.3, hatch='\\\\\\', label='EW Cut')
            except:
                pass

        ax.set_xticks([])
        
        lbl_1 = "Design Top Elev (m)" if include_crust else "Proposed Elev (m)"
        the_table = ax.table(cellText=cell_text, rowLabels=[lbl_1, "OGL Elev (m)", "Offset (m)"], loc='bottom', bbox=[0, -0.65, 1, 0.65])
        the_table.auto_set_font_size(False)
        the_table.set_fontsize(8)
        for (row, col), cell in the_table.get_celld().items():
            if col >= 0:
                cell.get_text().set_rotation(90)
                
        fig.text(0.30, 0.01, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
        fig.text(0.60, 0.01, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
        fig.text(0.90, 0.01, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        ax.set_title(f"{title_prefix} {current_ch}", pad=15)
        ax.set_ylabel("Elevation (m)")
        ax.grid(True, linestyle=':', alpha=
