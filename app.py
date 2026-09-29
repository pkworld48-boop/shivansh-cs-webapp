import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon
import io

st.set_page_config(page_title="Shiv Ansh Infra - C/S Web Studio", layout="wide")
st.title("Shiv Ansh Infra - Multi-Chainage C/S Studio")
st.markdown("Mobile ya PC se OGL aur FRL CSV upload karein aur direct PDF generate karein.")

def clean_chainage(val):
    if pd.isna(val): return "0"
    val_str = str(val).upper().replace('CH', '').replace(':', '').replace(',', '').strip()
    try:
        if '+' in val_str:
            parts = val_str.split('+')
            val_float = float(parts[0]) * 1000 + float(parts[1])
        else:
            val_float = float(val_str)
        f_val = round(val_float, 3)
        s_val = f"{f_val:.3f}".rstrip('0').rstrip('.')
        return s_val if s_val else "0"
    except Exception:
        return val_str

def calculate_toe_points(ogl_line, edge_x, edge_y, slope_ratio, is_left, max_toe):
    if slope_ratio == 0:
        vert_line = LineString([(edge_x, edge_y + 100), (edge_x, edge_y - 100)])
        inter = vert_line.intersection(ogl_line)
        ogl_y = inter.y if (not inter.is_empty and inter.geom_type == 'Point') else edge_y - 3
        return [(edge_x, ogl_y), (edge_x, edge_y)] if is_left else [(edge_x, edge_y), (edge_x, ogl_y)]
    vert_edge = LineString([(edge_x, edge_y + 100), (edge_x, edge_y - 100)])
    edge_inter = vert_edge.intersection(ogl_line)
    ogl_y_at_edge = edge_y - 1
    if not edge_inter.is_empty:
        if edge_inter.geom_type == 'Point': ogl_y_at_edge = edge_inter.y
        elif edge_inter.geom_type == 'MultiPoint': ogl_y_at_edge = edge_inter.geoms[0].y
    is_fill = edge_y >= ogl_y_at_edge 
    direction = -1 if is_left else 1
    ext_x = edge_x + direction * 200
    drop = 200 / slope_ratio
    slope_line = LineString([(edge_x, edge_y), (ext_x, edge_y - drop)]) if is_fill else LineString([(edge_x, edge_y), (ext_x, edge_y + drop)]) 
    inter = slope_line.intersection(ogl_line)
    int_x, int_y = None, None
    if not inter.is_empty:
        if inter.geom_type == 'Point': int_x, int_y = inter.x, inter.y
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
    else:
        return [(int_x, int_y)]

# Sidebar for Inputs
st.sidebar.header("📂 Data Upload")
ogl_file = st.sidebar.file_uploader("1. Upload OGL (CSV)", type=["csv"])
frl_file = st.sidebar.file_uploader("2. Upload FRL (CSV)", type=["csv"])

st.sidebar.header("⚙️ Design Parameters")
plot_title = st.sidebar.text_input("Title Prefix:", "Cross Section at CH:")
camber_val = st.sidebar.number_input("Camber (%):", value=2.5)

st.sidebar.subheader("Left Side")
l_width = abs(st.sidebar.number_input("L-Top Width (m):", value=0.1))
l_slope = st.sidebar.number_input("L-Slope (H:1) [0=Wall]:", value=2.0)
max_l_toe = -abs(st.sidebar.number_input("Max L-Toe Limit (m):", value=10.0))

st.sidebar.subheader("Right Side")
r_width = abs(st.sidebar.number_input("R-Top Width (m):", value=0.0))
r_slope = st.sidebar.number_input("R-Slope (H:1) [0=Wall]:", value=0.0)
max_r_toe = abs(st.sidebar.number_input("Max R-Toe Limit (m):", value=0.0))

if ogl_file and frl_file:
    try:
        ogl_df = pd.read_csv(ogl_file)
        ogl_df['Chainage'] = ogl_df['Chainage'].apply(clean_chainage)
        frl_df = pd.read_csv(frl_file)
        frl_dict = {}
        for _, row in frl_df.iterrows():
            try:
                ch_key = clean_chainage(row['Chainage'])
                frl_dict[ch_key] = float(row['FRL'])
            except Exception: pass

        chainages = ogl_df['Chainage'].unique()
        selected_ch = st.selectbox("📌 Select Chainage:", chainages)

        if selected_ch not in frl_dict:
            st.error(f"FRL Missing for CH: {selected_ch}")
        else:
            frl_val = frl_dict[selected_ch]
            st.success(f"FRL for CH {selected_ch}: **{frl_val:.3f} m**")
            
            ch_df = ogl_df[ogl_df['Chainage'] == selected_ch]
            offsets, elevations = ch_df['Offset'].tolist(), ch_df['Elevation'].tolist()
            ogl_points = sorted(list(zip(offsets, elevations)), key=lambda pt: pt[0])

            if ogl_points:
                extended_ogl = [(-500, ogl_points[0][1])] + ogl_points + [(500, ogl_points[-1][1])]
                ogl_line = LineString(extended_ogl)

                l_edge_x, r_edge_x = -l_width, r_width
                l_edge_y = frl_val - (l_width * (camber_val / 100.0))
                r_edge_y = frl_val - (r_width * (camber_val / 100.0))

                left_toe_pts = calculate_toe_points(ogl_line, l_edge_x, l_edge_y, l_slope, True, max_l_toe)
                right_toe_pts = calculate_toe_points(ogl_line, r_edge_x, r_edge_y, r_slope, False, max_r_toe)

                prop_pts = left_toe_pts + [(l_edge_x, l_edge_y), (0, frl_val), (r_edge_x, r_edge_y)] + right_toe_pts
                prop_x, prop_y = [p[0] for p in prop_pts], [p[1] for p in prop_pts]
                prop_line = LineString(prop_pts)

                plot_ogl_x, plot_ogl_y = [pt[0] for pt in ogl_points], [pt[1] for pt in ogl_points]
                if min(prop_x) < plot_ogl_x[0]: plot_ogl_x.insert(0, min(prop_x)); plot_ogl_y.insert(0, plot_ogl_y[0]) 
                if max(prop_x) > plot_ogl_x[-1]: plot_ogl_x.append(max(prop_x)); plot_ogl_y.append(plot_ogl_y[-1]) 

                fig, ax = plt.subplots(figsize=(10, 6))
                ax.plot(plot_ogl_x, plot_ogl_y, marker='o', linestyle='-', color='green', label='OGL', linewidth=2)
                ax.plot(prop_x, prop_y, marker='s', linestyle='-', color='blue', label='Proposed Profile', linewidth=2)
                ax.plot([0], [frl_val], marker='*', color='red', markersize=10, label=f'FRL ({frl_val}m)')

                min_y = min([y for x, y in ogl_points] + [y for x, y in prop_pts])
                datum_y = min_y - 10
                prop_poly = Polygon(prop_pts + [(prop_pts[-1][0], datum_y), (prop_pts[0][0], datum_y)])
                ogl_segment = [prop_pts[0]] + [(x, y) for x, y in ogl_points if prop_pts[0][0] < x < prop_pts[-1][0]] + [prop_pts[-1]]
                ogl_poly = Polygon(ogl_segment + [(prop_pts[-1][0], datum_y), (prop_pts[0][0], datum_y)])
                
                cut_area = ogl_poly.difference(prop_poly).area
                fill_area = prop_poly.difference(ogl_poly).area
                
                area_text = f"Earthwork Data:\nCut Area = {cut_area:.3f} sq.m\nFill Area = {fill_area:.3f} sq.m"
                ax.text(0.02, 0.95, area_text, transform=ax.transAxes, fontsize=10, verticalalignment='top', fontweight='bold', bbox=dict(boxstyle='round', facecolor='#F8F9FA', edgecolor='#6C757D', alpha=0.9))

                all_x_set = set([round(x, 3) for x in prop_x] + [round(x, 3) for x in plot_ogl_x])
                sorted_x = sorted(list(all_x_set))

                def get_elev(line, target_x):
                    vert = LineString([(target_x, -1000), (target_x, 1000)])
                    inter = line.intersection(vert)
                    if not inter.is_empty:
                        if inter.geom_type == 'Point': return f"{inter.y:.3f}"
                        if inter.geom_type == 'MultiPoint': return f"{inter.geoms[0].y:.3f}"
                        if inter.geom_type == 'LineString': return f"{inter.coords[0][1]:.3f}"
                    return "-"

                cell_text = [[get_elev(prop_line, x) for x in sorted_x], [get_elev(LineString(list(zip(plot_ogl_x, plot_ogl_y))), x) for x in sorted_x], [f"{x:.3f}" for x in sorted_x]]
                
                fig.subplots_adjust(left=0.18, bottom=0.45, right=0.98, top=0.92)
                ax.set_xticks([]) 
                the_table = ax.table(cellText=cell_text, rowLabels=["Proposed Elev (m)", "OGL Elev (m)", "Offset (m)"], loc='bottom', bbox=[0, -0.35, 1, 0.25])
                the_table.auto_set_font_size(False)
                the_table.set_fontsize(9)
                the_table.scale(1, 1.5)
                
                fig.text(0.20, 0.03, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
                fig.text(0.50, 0.03, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
                fig.text(0.80, 0.03, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
                
                ax.set_title(f"{plot_title} {selected_ch}") 
                ax.set_ylabel("Elevation (m)")
                ax.grid(True, linestyle=':', alpha=0.7)
                ax.legend(loc="upper right")

                st.pyplot(fig)

                buf = io.BytesIO()
                fig.savefig(buf, format="pdf", bbox_inches='tight', dpi=300)
                st.download_button(label="🖨️ Download Final PDF", data=buf.getvalue(), file_name=f"CS_CH_{selected_ch}.pdf", mime="application/pdf")

    except Exception as e:
        st.error(f"Koi error aayi hai: {e}")
else:
    st.info("👈 Left side (Sidebar) se apni OGL aur FRL files upload karein.")