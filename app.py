import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon
import io
import zipfile

# ================= PAGE SETUP & CSS =================
st.set_page_config(page_title="Shiv Ansh Infra Earthwork CS Engine", layout="wide")

# CSS to remove extra top space and hide default elements
custom_css = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
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

st.title("Shiv Ansh Infra Earthwork CS Engine")

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
ogl_file = st.sidebar.file_uploader("Upload OGL CSV", type=['csv'])
frl_file = st.sidebar.file_uploader("Upload FRL CSV", type=['csv'])

if ogl_file:
    df = pd.read_csv(ogl_file)
    df['Chainage'] = df['Chainage'].apply(lambda x: f"{float(x):g}" if pd.notnull(x) else str(x))
    st.session_state.ogl_df = df

if frl_file:
    df_f = pd.read_csv(frl_file)
    st.session_state.frl_dict = {f"{float(row['Chainage']):g}": float(row['FRL']) for _, row in df_f.iterrows() if pd.notnull(row['Chainage'])}

st.sidebar.header("⚙️ Parameters")
title_prefix = st.sidebar.text_input("Plot Title Prefix", "Cross Section at CH: ")
camber_val = st.sidebar.number_input("Camber (%)", value=2.5, format="%.2f")

col1, col2 = st.sidebar.columns(2)
with col1:
    st.markdown("**LEFT SIDE**")
    l_width = abs(st.number_input("L-Width", value=10.0))
    l_slope = st.number_input("L-Slope (H:1)", value=2.0)
    max_l_toe = -abs(st.number_input("Max L-Toe", value=30.0))
with col2:
    st.markdown("**RIGHT SIDE**")
    r_width = abs(st.number_input("R-Width", value=10.0))
    r_slope = st.number_input("R-Slope (H:1)", value=2.0)
    max_r_toe = abs(st.number_input("Max R-Toe", value=30.0))

# ================= MAIN AREA =================
if not st.session_state.ogl_df.empty:
    chainages = st.session_state.ogl_df['Chainage'].unique()
    
    # Dropdown in a smaller column
    col_sel, col_msg = st.columns([2, 10])
    with col_sel:
        ch_sel = st.selectbox("Select Chainage", chainages)
        
    frl_val = st.session_state.frl_dict.get(ch_sel, None)
    
    with col_msg:
        st.write("") # For vertical alignment
        if frl_val is not None:
            st.success(f"Active FRL: {frl_val} m")
        else:
            st.error("FRL Data Missing for this Chainage!")

    tab1, tab2 = st.tabs(["Cross Section", "L-Section"])

    def get_elev(line, target_x):
        vert = LineString([(target_x, -1000), (target_x, 1000)])
        inter = line.intersection(vert)
        if not inter.is_empty:
            return f"{inter.y:.3f}" if inter.geom_type == 'Point' else f"{inter.geoms[0].y:.3f}"
        min_x, min_y, max_x, max_y = line.bounds
        if abs(target_x - min_x) <= 0.005:
            return f"{next((p[1] for p in line.coords if p[0] == min_x), line.coords[0][1]):.3f}"
        if abs(target_x - max_x) <= 0.005:
            return f"{next((p[1] for p in line.coords if p[0] == max_x), line.coords[-1][1]):.3f}"
        return "-"

    def draw_cs(current_ch):
        ch_df = st.session_state.ogl_df[st.session_state.ogl_df['Chainage'] == current_ch].copy()
        if ch_df.empty or current_ch not in st.session_state.frl_dict:
            return None
        frl_v = st.session_state.frl_dict[current_ch]
        ogl_points = sorted(list(zip(ch_df['Offset'].tolist(), ch_df['Elevation'].tolist())), key=lambda pt: pt[0])
        ogl_line = LineString([(-500, ogl_points[0][1])] + ogl_points + [(500, ogl_points[-1][1])])
        l_edge_y = frl_v - (l_width * (camber_val / 100.0))
        r_edge_y = frl_v - (r_width * (camber_val / 100.0))
        
        prop_pts = calculate_toe_points(ogl_line, -l_width, l_edge_y, l_slope, True, max_l_toe) + \
                   [(-l_width, l_edge_y), (0, frl_v), (r_width, r_edge_y)] + \
                   calculate_toe_points(ogl_line, r_width, r_edge_y, r_slope, False, max_r_toe)
        
        prop_x, prop_y = [p[0] for p in prop_pts], [p[1] for p in prop_pts]
        prop_line = LineString(prop_pts)
        plot_ogl_x, plot_ogl_y = [pt[0] for pt in ogl_points], [pt[1] for pt in ogl_points]
        
        if min(prop_x) < plot_ogl_x[0]:
            plot_ogl_x.insert(0, min(prop_x)); plot_ogl_y.insert(0, plot_ogl_y[0])
        if max(prop_x) > plot_ogl_x[-1]:
            plot_ogl_x.append(max(prop_x)); plot_ogl_y.append(plot_ogl_y[-1])
            
        fig, ax = plt.subplots(figsize=(11, 7.8))
        ax.plot(plot_ogl_x, plot_ogl_y, marker='o', color='green', label='OGL', linewidth=2)
        ax.plot(prop_x, prop_y, marker='s', color='blue', label='Proposed Profile', linewidth=2)
        
        # FRL Point and Dotted Line up to OGL
        ax.plot([0], [frl_v], marker='*', color='red', markersize=10, label=f'FRL ({frl_v}m)')
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
            ax.text(0.02, 0.95, f"Cut Area = {cut_area:.3f} sq.m\nFill Area = {fill_area:.3f} sq.m", transform=ax.transAxes, fontsize=10, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
        except:
            pass

        sorted_x = sorted(list(set([round(x, 3) for x in prop_x] + [round(x, 3) for x in plot_ogl_x])))
            
        cell_text = [[get_elev(prop_line, x) for x in sorted_x], [get_elev(ogl_line, x) for x in sorted_x], [f"{x:.3f}" for x in sorted_x]]
        
        try:
            nan = float('nan')
            y_p = [float(y) if y != "-" else nan for y in cell_text[0]]
            y_o = [float(y) if y != "-" else nan for y in cell_text[1]]
            ax.fill_between(sorted_x, y_o, y_p, where=[p >= o for p, o in zip(y_p, y_o)], interpolate=True, facecolor='lightblue', edgecolor='blue', alpha=0.4, hatch='///', label='Fill Hatch')
            ax.fill_between(sorted_x, y_o, y_p, where=[p < o for p, o in zip(y_p, y_o)], interpolate=True, facecolor='lightpink', edgecolor='red', alpha=0.4, hatch='\\\\\\', label='Cut Hatch')
        except:
            pass

        fig.subplots_adjust(left=0.150, bottom=0.60, right=0.95, top=0.92)
        ax.set_xticks([])
        the_table = ax.table(cellText=cell_text, rowLabels=["Proposed Elev (m)", "OGL Elev (m)", "Offset (m)"], loc='bottom', bbox=[0, -0.8, 1, 0.7])
        the_table.auto_set_font_size(False)
        the_table.set_fontsize(9)
        for (row, col), cell in the_table.get_celld().items():
            if col >= 0:
                cell.get_text().set_rotation(90)
                
        fig.text(0.20, 0.03, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
        fig.text(0.50, 0.03, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
        fig.text(0.80, 0.03, "________________________\n(Seal & Sign)", ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        ax.set_title(f"{title_prefix} {current_ch}")
        ax.set_ylabel("Elevation (m)")
        ax.grid(True, linestyle=':', alpha=0.7)
        ax.legend(loc="upper right", framealpha=1.0)
        
        x_span = max(sorted_x) - min(sorted_x) if sorted_x else 20
        ax.set_xlim(min(sorted_x) - x_span * 0.05, max(sorted_x) + x_span * 0.20)
        y_min, y_max = ax.get_ylim()
        ax.set_ylim(y_min - (y_max - y_min)*0.05, y_max + (y_max - y_min) * 0.55)
        
        return fig

    with tab1:
        if frl_val is not None:
            fig_cs = draw_cs(ch_sel)
            if fig_cs:
                # यहाँ हमने स्क्रीन को दो हिस्सों में बाँटा है (70% ग्राफ के लिए, 30% टेबल के लिए)
                col_graph, col_edit = st.columns([7, 3], gap="medium")
                
                with col_graph:
                    st.subheader("Cross Section Preview")
                    st.pyplot(fig_cs)
                    buf = io.BytesIO()
                    fig_cs.savefig(buf, format="pdf", bbox_inches="tight")
                    st.download_button(label=f"🖨️ Download C/S CH:{ch_sel} (PDF)", data=buf.getvalue(), file_name=f"CS_{ch_sel}.pdf", mime="application/pdf", use_container_width=True)
                
                with col_edit:
                    st.subheader("✏️ Edit OGL Data")
                    st.info("डेटा बदलने के बाद नीचे 'Update Graph' बटन दबाएँ।")
                    current_ch_df = st.session_state.ogl_df[st.session_state.ogl_df['Chainage'] == ch_sel].copy()
                    
                    # फॉर्म लगाने से ऐप हैंग नहीं होगा
                    with st.form(key=f"edit_form_{ch_sel}"):
                        edited_ch_df = st.data_editor(current_ch_df, use_container_width=True, num_rows="dynamic", hide_index=True)
                        submit_button = st.form_submit_button(label="🔄 Update Graph", use_container_width=True)
                        
                        if submit_button:
                            if not edited_ch_df.equals(current_ch_df):
                                other_df = st.session_state.ogl_df[st.session_state.ogl_df['Chainage'] != ch_sel]
                                st.session_state.ogl_df = pd.concat([other_df, edited_ch_df], ignore_index=True)
                                st.rerun()

    with tab2:
        st.subheader("L-Section Profile")
        if st.session_state.frl_dict:
            ch_list = []
            for c in chainages:
                try:
                    ch_list.append((float(c), c))
                except:
                    pass
            ch_list.sort(key=lambda x: x[0])
            chainages_num, ogl_elevs, frl_elevs = [], [], []
            for num, c_str in ch_list:
                if c_str in st.session_state.frl_dict:
                    df_c = st.session_state.ogl_df[st.session_state.ogl_df['Chainage'] == c_str].copy()
                    center_row = df_c.loc[df_c['Offset'].astype(float).abs().idxmin()]
                    chainages_num.append(num)
                    ogl_elevs.append(float(center_row['Elevation']))
                    frl_elevs.append(st.session_state.frl_dict[c_str])
            if chainages_num:
                fig_l, ax_l = plt.subplots(figsize=(12, 6))
                ax_l.plot(chainages_num, ogl_elevs, marker='o', color='green', label='Center OGL')
                ax_l.plot(chainages_num, frl_elevs, marker='s', color='red', label='Proposed FRL')
                ax_l.fill_between(chainages_num, ogl_elevs, frl_elevs, where=[f >= o for f, o in zip(frl_elevs, ogl_elevs)], color='blue', alpha=0.15, label='Fill Area')
                ax_l.fill_between(chainages_num, ogl_elevs, frl_elevs, where=[f < o for f, o in zip(frl_elevs, ogl_elevs)], color='red', alpha=0.15, label='Cut Area')
                fig_l.subplots_adjust(left=0.15, bottom=0.55, right=0.95, top=0.90)
                ax_l.set_xticks([])
                row_frl = [f"{v:.3f}" for v in frl_elevs]
                row_ogl = [f"{v:.3f}" for v in ogl_elevs]
                row_ch = [f"{v:g}" for v in chainages_num]
                t_table = ax_l.table(cellText=[row_frl, row_ogl, row_ch], rowLabels=["Proposed FRL (m)", "Center OGL (m)", "Chainage (m)"], loc='bottom', bbox=[0, -1.1, 1, 0.9])
                t_table.auto_set_font_size(False)
                t_table.set_fontsize(8)
                for (row, col), cell in t_table.get_celld().items():
                    if col >= 0:
                        cell.get_text().set_rotation(90)
                ax_l.set_title("Longitudinal Section (L-Section)", fontweight='bold')
                ax_l.set_ylabel("Elevation (m)")
                ax_l.grid(True, linestyle=':', alpha=0.7)
                ax_l.legend(loc="upper right")
                true_y_min = min(ogl_elevs + frl_elevs)
                true_y_max = max(ogl_elevs + frl_elevs)
                ax_l.set_ylim(true_y_min - 3, true_y_max + 5)
                x_span = max(chainages_num) - min(chainages_num) if chainages_num else 100
                ax_l.set_xlim(min(chainages_num) - x_span * 0.05, max(chainages_num) + x_span * 0.25)
                st.pyplot(fig_l)
                buf_l = io.BytesIO()
                fig_l.savefig(buf_l, format="pdf", bbox_inches="tight")
                st.download_button(label="🖨️ Download L-Section (PDF)", data=buf_l.getvalue(), file_name="L_Section.pdf", mime="application/pdf")

    st.markdown("---")
    st.subheader("📦 Advanced Exports")
    if st.button("📦 Generate Batch PDF (ZIP)"):
        with st.spinner("Generating all PDFs... Please wait..."):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for c in chainages:
                    if c in st.session_state.frl_dict:
                        f = draw_cs(c)
                        if f:
                            b = io.BytesIO()
                            f.savefig(b, format="pdf", bbox_inches="tight")
                            zf.writestr(f"CS_CH_{c}.pdf", b.getvalue())
                            plt.close(f)
            st.success("Batch Generated!")
            st.download_button(label="⬇️ Download All PDFs (ZIP)", data=zip_buffer.getvalue(), file_name="All_Cross_Sections.zip", mime="application/zip")

    if st.button("📊 Calculate Trapezoidal Earthwork Qty"):
        with st.spinner("Calculating volumes..."):
            ch_list = []
            for c in chainages:
                try:
                    ch_list.append((float(c), c))
                except:
                    pass
            ch_list.sort(key=lambda x: x[0])
            qty_data = []
            prev_ch, prev_cut, prev_fill = None, 0.0, 0.0
            cum_cut, cum_fill = 0.0, 0.0
            for ch_num, ch_str in ch_list:
                if ch_str not in st.session_state.frl_dict: continue
                ch_df = st.session_state.ogl_df[st.session_state.ogl_df['Chainage'] == ch_str].copy()
                ogl_points = sorted(list(zip(ch_df['Offset'].tolist(), ch_df['Elevation'].tolist())), key=lambda pt: pt[0])
                ogl_line = LineString([(-500, ogl_points[0][1])] + ogl_points + [(500, ogl_points[-1][1])])
                frl_v = st.session_state.frl_dict[ch_str]
                l_e = frl_v - (l_width * (camber_val / 100.0))
                r_e = frl_v - (r_width * (camber_val / 100.0))
                prop_pts = calculate_toe_points(ogl_line, -l_width, l_e, l_slope, True, max_l_toe) + [(-l_width, l_e), (0, frl_v), (r_width, r_e)] + calculate_toe_points(ogl_line, r_width, r_e, r_slope, False, max_r_toe)
                cut_area, fill_area = 0.0, 0.0
                try:
                    datum_y = min([y for x, y in ogl_points] + [y for x, y in prop_pts]) - 10
                    prop_poly = Polygon(prop_pts + [(prop_pts[-1][0], datum_y), (prop_pts[0][0], datum_y)])
                    ogl_poly = Polygon([prop_pts[0]] + [(x, y) for x, y in ogl_points if prop_pts[0][0] < x < prop_pts[-1][0]] + [prop_pts[-1], (prop_pts[-1][0], datum_y), (prop_pts[0][0], datum_y)])
                    cut_area = ogl_poly.difference(prop_poly).area
                    fill_area = prop_poly.difference(ogl_poly).area
                except:
                    pass
                L = ch_num - prev_ch if prev_ch is not None else 0.0
                c_vol = (L / 2.0) * (prev_cut + cut_area) if prev_ch is not None else 0.0
                f_vol = (L / 2.0) * (prev_fill + fill_area) if prev_ch is not None else 0.0
                cum_cut += c_vol
                cum_fill += f_vol
                qty_data.append({"Chainage": ch_str, "Length (L)": round(L,3), "Cut Area": round(cut_area,3), "Fill Area": round(fill_area,3), "Cut Vol": round(c_vol,3), "Fill Vol": round(f_vol,3), "Cum Cut": round(cum_cut,3), "Cum Fill": round(cum_fill,3)})
                prev_ch, prev_cut, prev_fill = ch_num, cut_area, fill_area
            if qty_data:
                df_qty = pd.DataFrame(qty_data)
                st.dataframe(df_qty)
                csv = df_qty.to_csv(index=False).encode('utf-8')
                st.download_button(label="⬇ Download QTY Sheet (CSV)", data=csv, file_name="Earthwork_Qty_Sheet.csv", mime="text/csv")
else:
    st.info("Please upload OGL CSV from the sidebar to begin.")
