import os
import re
import json
import tempfile
import shutil
import streamlit as st
import html
import pandas as pd

PATTERNS_FILE = os.path.join(os.path.expanduser("~"), ".textproc_patterns.json")

COMMON_PATTERNS = {
    "Select a common pattern...": {"pattern": "", "case_sensitive": False, "replace_with": ""},
    "Email Address": {"pattern": r"[\w\.\-]+@[\w\.\-]+\.\w+", "case_sensitive": False, "replace_with": ""},
    "URL (http/https)": {"pattern": r"https?://[^\s/$.?#].[^\s]*", "case_sensitive": False, "replace_with": ""},
    "Phone Number (U.S.)": {"pattern": r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", "case_sensitive": False, "replace_with": ""},
    "Date (YYYY-MM-DD)": {"pattern": r"\d{4}-\d{2}-\d{2}", "case_sensitive": False, "replace_with": ""},
    "IP Address (IPv4)": {"pattern": r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "case_sensitive": False, "replace_with": ""},
    "HTML Tag": {"pattern": r"<([a-z][a-z0-9]*)\b[^>]*>(.*?)</\1>", "case_sensitive": False, "replace_with": ""},
}

def compile_pattern(pattern, case_sensitive, multiline=False, dotall=False):
    flags = 0 if case_sensitive else re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE
    if dotall:
        flags |= re.DOTALL
    return re.compile(pattern, flags)

def explain_regex(pattern):
    explanation = []
    
    token_map = {
        '.': "**Any Character** (`.`): Matches any single character except a newline (unless DOTALL flag is used).",
        '^': "**Start of String/Line** (`^`): Asserts the position at the start of the string (or the start of a line in MULTILINE mode).",
        '$': "**End of String/Line** (`$`): Asserts the position at the end of the string (or the end of a line in MULTILINE mode).",
        '\\d': "**Digit** (`\\d`): Matches any digit from 0 to 9.",
        '\\D': "**Not a Digit** (`\\D`): Matches any character that is not a digit.",
        '\\w': "**Word Character** (`\\w`): Matches any letter (a-z, A-Z), digit (0-9), or underscore (_).",
        '\\W': "**Not a Word Character** (`\\W`): Matches any character that is not a letter, digit, or underscore.",
        '\\s': "**Whitespace** (`\\s`): Matches any whitespace character (like space, tab, newline).",
        '\\S': "**Not Whitespace** (`\\S`): Matches any character that is not whitespace.",
        '\\b': "**Word Boundary** (`\\b`): Asserts a position at a word boundary (e.g., between a letter and a space).",
        '\\B': "**Not a Word Boundary** (`\\B`): Asserts a position that is not a word boundary.",
    }

    i = 0
    while i < len(pattern):
        char = pattern[i]
        token = char
        
        if char == '\\':
            if i + 1 < len(pattern):
                token = pattern[i:i+2]
                if token in token_map:
                    explanation.append(f"- {token_map[token]}")
                    i += 2
                    continue
                else:
                    explanation.append(f"- **Literal Character** (`{token}`): Matches the character '{pattern[i+1]}' literally.")
                    i += 2
                    continue
        
        if token in token_map:
            explanation.append(f"- {token_map[token]}")
            i += 1
            continue

        if char in '*+?':
            quantifier_map = {
                '*': "**Zero or More** (`*`): The preceding element can occur 0 or more times.",
                '+': "**One or More** (`+`): The preceding element must occur 1 or more times.",
                '?': "**Zero or One** (`?`): The preceding element can occur 0 or 1 time. It also makes a quantifier 'non-greedy'.",
            }
            explanation.append(f"- {quantifier_map[char]}")
            i += 1
            continue
            
        if char == '{':
            match = re.match(r'\{(\d+)(,)?(\d+)?\}', pattern[i:])
            if match:
                quant_token = match.group(0)
                g1, g2, g3 = match.groups()
                if g2 is None and g3 is None:
                    desc = f"exactly {g1} times"
                elif g3 is None:
                    desc = f"at least {g1} times"
                else:
                    desc = f"between {g1} and {g3} times"
                explanation.append(f"- **Quantifier** (`{quant_token}`): The preceding element must occur {desc}.")
                i += len(quant_token)
                continue

        if char == '(':
            group_desc = "**Capturing Group** (`(`...`)`): Groups multiple tokens together and creates a capture group to extract the matched substring."
            if pattern[i:i+3] == '(?:':
                 group_desc = "**Non-Capturing Group** (`(?:`...`)`): Groups tokens together without creating a capture group."
                 i += 2
            elif pattern[i:i+2] == '(?':
                explanation.append("- **Lookaround/Conditional** (`(?`...`)`): A special group that asserts a condition (e.g., lookahead, lookbehind) without consuming characters.")
                i += 1
                continue

            explanation.append(f"- {group_desc}")
            i += 1
            continue
        if char == ')':
            explanation.append("- **End Group** (`)`): Closes the current group.")
            i += 1
            continue
        if char == '|':
            explanation.append("- **Alternation / OR** (`|`): Acts like a boolean OR, matching the expression before or after it.")
            i += 1
            continue
            
        if char == '[':
            set_desc = "**Character Set** (`[`...`]`) : Matches any single character from the set."
            if pattern[i+1:i+2] == '^':
                set_desc = "**Negated Character Set** (`[^`...`]`) : Matches any single character *not* in the set."
                i += 1
            explanation.append(f"- {set_desc}")
            i += 1
            continue
        if char == ']':
            explanation.append("- **End Character Set** (`]`): Closes the character set.")
            i += 1
            continue

        explanation.append(f"- **Literal Character** (`{char}`): Matches the character '{char}' literally.")
        i += 1
        
    if not explanation:
        return ["- This pattern appears to be empty or contains no standard regex tokens to explain."]

    return explanation


def load_patterns_file():
    if not os.path.exists(PATTERNS_FILE):
        return []
    try:
        with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []

def save_patterns_file(patterns):
    try:
        with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
            json.dump(patterns, f, ensure_ascii=False, indent=2)
    except IOError as e:
        st.error(f"Failed to save patterns: {e}")

def save_uploaded_to_tmp(uploaded_file):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb") as tmp:
            tmp.write(uploaded_file.getvalue())
            return tmp.name
    except Exception as e:
        st.error(f"Error saving uploaded file: {e}")
        return None

def stream_read_file(path, progress_bar, placeholder):
    try:
        total_size = os.path.getsize(path)
    except OSError:
        total_size = None

    content_accumulator = []
    bytes_read = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fr:
            for line in fr:
                content_accumulator.append(line)
                bytes_read += len(line.encode("utf-8", errors="replace"))
                if total_size:
                    progress = min(int(bytes_read * 100 / total_size), 100)
                    progress_bar.progress(progress)
        if total_size:
            progress_bar.progress(100)
        return "".join(content_accumulator)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return ""


def save_editor_content_to_file(path, content):
    try:
        backup_path = path + ".bak"
        if os.path.exists(path):
            shutil.copy2(path, backup_path)
        else:
            backup_path = None

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return True, backup_path
    except Exception as e:
        return False, f"Error while saving file: {e}"

def live_highlight():
    pattern = st.session_state.get("pattern_input", "")
    case_sensitive = st.session_state.get("case_sensitive_input", False)
    multiline = st.session_state.get("multiline_input", False)
    dotall = st.session_state.get("dotall_input", False)
    text_content = st.session_state.get("editor_content", "")
    color = st.session_state.get("color_input", "yellow")
    
    output_html = ""
    match_count = 0
    
    if not pattern or not text_content:
        st.session_state.highlight_output = "<p style='color:grey; font-family:monospace;'>Enter a pattern to see live highlighting.</p>"
        st.session_state.match_count = 0
        return
        
    try:
        cp = compile_pattern(pattern, case_sensitive, multiline, dotall)
        matches = list(cp.finditer(text_content))
        match_count = len(matches)
        
        if not matches:
            output_html = "<p style='color:grey; font-family:monospace;'>No matches found.</p>"
        else:
            last_end = 0
            for m in matches:
                output_html += html.escape(text_content[last_end:m.start()])
                match_text = html.escape(text_content[m.start():m.end()])
                output_html += f'<mark style="background-color:{color};">{match_text}</mark>'
                last_end = m.end()
            output_html += html.escape(text_content[last_end:])
            output_html = f'<div style="white-space:pre-wrap; font-family: monospace;">{output_html}</div>'

    except re.error as e:
        output_html = f'<p style="color:red; font-family: monospace;">Invalid Regex: {e}</p>'
    
    st.session_state.highlight_output = output_html
    st.session_state.match_count = match_count

def insert_token(token):
    st.session_state.pattern_input += token
    live_highlight()

def load_common_pattern():
    library_choice = st.session_state.library_selectbox
    if library_choice != "Select a common pattern...":
        p = COMMON_PATTERNS[library_choice]
        st.session_state.pattern_input = p.get("pattern", "")
        st.session_state.case_sensitive_input = p.get("case_sensitive", False)
        st.session_state.replace_with_input = p.get("replace_with", "")
        st.session_state.multiline_input = False
        st.session_state.dotall_input = False
        st.toast(f"Loaded '{library_choice}' pattern")
        live_highlight()

def load_saved_pattern():
    sel = st.session_state.get("saved_pattern_selection")
    if not sel:
        return
    patterns = st.session_state.patterns
    options = [f"{p.get('name', 'unnamed')} | {'CS' if p.get('case_sensitive') else 'CI'} | {p.get('pattern', '')}" for p in patterns]
    if sel in options:
        idx = options.index(sel)
        p = patterns[idx]
        st.session_state.pattern_input = p.get("pattern", "")
        st.session_state.case_sensitive_input = p.get("case_sensitive", False)
        st.session_state.color_input = p.get("color", "yellow")
        st.session_state.pattern_name = p.get("name", "")
        st.session_state.replace_with_input = p.get("replace_with", "")
        st.session_state.multiline_input = p.get("multiline", False)
        st.session_state.dotall_input = p.get("dotall", False)
        st.toast(f"Loaded pattern '{p.get('name', '')}'")
        live_highlight()
        
def replace_editor_content():
    if not st.session_state.editor_content:
        st.toast("⚠️ Editor is empty. Load a file first.")
        return
    pattern = st.session_state.get("pattern_input")
    if not pattern:
        st.toast("⚠️ Enter a regex pattern for replacement.")
        return

    try:
        case_sensitive = st.session_state.get("case_sensitive_input", False)
        multiline = st.session_state.get("multiline_input", False)
        dotall = st.session_state.get("dotall_input", False)
        replace_with = st.session_state.get("replace_with_input", "")
        
        cp = compile_pattern(pattern, case_sensitive, multiline, dotall)
        
        original = st.session_state.editor_content
        st.session_state.last_editor_content = original
        
        replaced = cp.sub(replace_with, original)
        st.session_state.editor_content = replaced
        live_highlight()
        st.toast("✅ Replacement complete.")
    except re.error as e:
        st.error(f"Invalid regex: {e}")

def undo_editor_content():
    if "last_editor_content" in st.session_state and st.session_state.last_editor_content is not None:
        st.session_state.editor_content = st.session_state.last_editor_content
        st.session_state.last_editor_content = None
        live_highlight()
        st.toast("✅ Undo complete.")
    else:
        st.toast("No editor action to undo.")

st.set_page_config(page_title="Text Processing Pro", layout="wide")
st.title("✨ Text Processing Pro")

if 'pattern_input' not in st.session_state:
    st.session_state.pattern_input = ""
if 'replace_with_input' not in st.session_state:
    st.session_state.replace_with_input = ""
if 'case_sensitive_input' not in st.session_state:
    st.session_state.case_sensitive_input = False
if 'multiline_input' not in st.session_state:
    st.session_state.multiline_input = False
if 'dotall_input' not in st.session_state:
    st.session_state.dotall_input = False
if 'color_input' not in st.session_state:
    st.session_state.color_input = "yellow"

if "patterns" not in st.session_state:
    st.session_state.patterns = load_patterns_file()
if "last_backup" not in st.session_state:
    st.session_state.last_backup = None
if "editor_content" not in st.session_state:
    st.session_state.editor_content = ""
if "last_editor_content" not in st.session_state:
    st.session_state.last_editor_content = None
if "highlight_output" not in st.session_state:
    st.session_state.highlight_output = "<p style='color:grey; font-family:monospace;'>Load a file or paste text to get started.</p>"
if "match_count" not in st.session_state:
    st.session_state.match_count = 0
if "file_path" not in st.session_state:
    st.session_state.file_path = None
if "file_origin" not in st.session_state:
    st.session_state.file_origin = None
if "original_filename" not in st.session_state:
    st.session_state.original_filename = "processed_file.txt"


col1, col2 = st.columns([3, 2])

with col1:
    with st.container(border=True):
        st.subheader("📂 Load File")
        uploaded_file = st.file_uploader("Upload a text file", type=["txt"], label_visibility="collapsed")
        local_path = st.text_input("Or, enter a local file path (on the server)", placeholder="e.g., /path/to/your/file.txt")
        load_button = st.button("Load File to Editor", use_container_width=True, type="primary")

    with st.container(border=True):
        st.subheader("✍️ Define Pattern")
        pattern = st.text_input("Regex Pattern", key="pattern_input", placeholder="Enter your regex here", on_change=live_highlight)
        replace_with = st.text_input("Replacement Text", key="replace_with_input", placeholder="Enter text to replace matches with")
        
        st.markdown("**Options:**")
        opt_cols = st.columns(4)
        with opt_cols[0]:
            case_sensitive = st.checkbox("Case sensitive", key="case_sensitive_input", on_change=live_highlight)
        with opt_cols[1]:
            multiline = st.checkbox("Multiline (^/$)", help="Allows `^` and `$` to match the start and end of lines, not just the whole string.", key="multiline_input", on_change=live_highlight)
        with opt_cols[2]:
            dotall = st.checkbox("Dotall (.)", help="Allows `.` to match any character, including newlines.", key="dotall_input", on_change=live_highlight)
        with opt_cols[3]:
            color = st.selectbox("Highlight", 
                                ("yellow", "red", "green", "cyan", "magenta", "blue"),
                                key="color_input", label_visibility="collapsed", on_change=live_highlight)

    with st.container(border=True):
        st.subheader("🚀 Execute")
        action_cols = st.columns(3)
        btn_capture = action_cols[0].button("🎯 Capture Groups", use_container_width=True)
        action_cols[1].button("📝 Replace in Editor", use_container_width=True, on_click=replace_editor_content)
        
        with action_cols[2]:
            file_origin = st.session_state.get("file_origin")
            if file_origin == 'local':
                btn_save_to_file = st.button("💾 Save to File", use_container_width=True)
            elif file_origin == 'upload':
                st.download_button(
                    label="💾 Download File",
                    data=st.session_state.get("editor_content", "").encode("utf-8"),
                    file_name=f"processed_{st.session_state.original_filename}",
                    mime="text/plain",
                    use_container_width=True
                )
            else:
                st.button("💾 Save / Download", use_container_width=True, disabled=True, help="Load a file to enable this action")


with col2:
    with st.expander("🛠️ Regex Cheatsheet", expanded=True):
        cheatsheet_cols = st.columns(4)
        cheatsheet_cols[0].button("Digit `\\d`", use_container_width=True, on_click=insert_token, args=(r"\d",))
        cheatsheet_cols[1].button("Word `\\w`", use_container_width=True, on_click=insert_token, args=(r"\w",))
        cheatsheet_cols[2].button("Space `\\s`", use_container_width=True, on_click=insert_token, args=(r"\s",))
        cheatsheet_cols[3].button("Any `.`", use_container_width=True, on_click=insert_token, args=(r".",))
        
        cheatsheet_cols[0].button("Start `^`", use_container_width=True, on_click=insert_token, args=(r"^",))
        cheatsheet_cols[1].button("End `$`", use_container_width=True, on_click=insert_token, args=(r"$",))
        cheatsheet_cols[2].button("Group `()`", use_container_width=True, on_click=insert_token, args=(r"()",))
        cheatsheet_cols[3].button("Set `[]`", use_container_width=True, on_click=insert_token, args=(r"[]",))

        cheatsheet_cols[0].button("0+ `*`", use_container_width=True, on_click=insert_token, args=(r"*",))
        cheatsheet_cols[1].button("1+ `+`", use_container_width=True, on_click=insert_token, args=(r"+",))
        cheatsheet_cols[2].button("0 or 1 `?`", use_container_width=True, on_click=insert_token, args=(r"?",))
        cheatsheet_cols[3].button("Or `|`", use_container_width=True, on_click=insert_token, args=(r"|",))

    with st.container(border=True):
        st.subheader("📚 Libraries")
        library_choice = st.selectbox(
            "Load from built-in library", 
            options=list(COMMON_PATTERNS.keys()),
            key="library_selectbox",
            on_change=load_common_pattern
        )
        st.divider()
        patterns = st.session_state.patterns
        options = [f"{p.get('name', 'unnamed')} | {'CS' if p.get('case_sensitive') else 'CI'} | {p.get('pattern', '')}" for p in patterns]
        
        if options:
            sel = st.selectbox("Load from your saved patterns", options, key="saved_pattern_selection", index=None, placeholder="Select a saved pattern")
        else:
            st.info("No saved patterns yet.")
            sel = None
        
        name = st.text_input("Pattern name for saving", key="pattern_name", placeholder="Name for current pattern")

        btn_cols = st.columns(3)
        save_pat = btn_cols[0].button("Save", use_container_width=True)
        load_pat = btn_cols[1].button("Load", use_container_width=True, on_click=load_saved_pattern, disabled=not sel)
        delete_pat = btn_cols[2].button("Delete", use_container_width=True, disabled=not sel)

    with st.container(border=True):
        st.subheader("🧐 Helper")
        if st.button("Explain Current Pattern", use_container_width=True):
            if st.session_state.pattern_input:
                with st.expander("Explanation", expanded=True):
                    explanation = explain_regex(st.session_state.pattern_input)
                    for part in explanation:
                        st.markdown(part)
            else:
                st.toast("Enter a pattern to explain.")
    
    with st.container(border=True):
        st.subheader("⏪ History")
        undo_cols = st.columns(2)
        undo_cols[0].button("Undo in Editor", use_container_width=True, on_click=undo_editor_content)
        undo_file = undo_cols[1].button("Restore Backup", use_container_width=True)

if save_pat:
    if not st.session_state.pattern_input:
        st.toast("⚠️ Enter a pattern to save.")
    else:
        pname = st.session_state.pattern_name or f"pattern_{len(patterns) + 1}"
        new_pattern = {
            "name": pname,
            "pattern": st.session_state.pattern_input,
            "case_sensitive": st.session_state.case_sensitive_input,
            "multiline": st.session_state.multiline_input,
            "dotall": st.session_state.dotall_input,
            "color": st.session_state.color_input,
            "replace_with": st.session_state.replace_with_input
        }
        patterns.append(new_pattern)
        save_patterns_file(patterns)
        st.session_state.patterns = patterns
        st.toast(f"✅ Saved pattern '{pname}'")
        st.rerun()


if delete_pat and sel:
    idx = options.index(sel)
    name_del = patterns[idx].get("name", "unnamed")
    patterns.pop(idx)
    save_patterns_file(patterns)
    st.session_state.patterns = patterns
    st.toast(f"🗑️ Deleted pattern '{name_del}'")
    st.rerun()

current_run_file_path = None
file_origin_for_run = None
if uploaded_file:
    current_run_file_path = save_uploaded_to_tmp(uploaded_file)
    file_origin_for_run = "upload"
elif local_path and os.path.exists(local_path):
    current_run_file_path = local_path
    file_origin_for_run = "local"
elif local_path:
    st.warning("Local path does not exist on the server.")

if load_button and current_run_file_path:
    with st.spinner("Loading file..."):
        content = stream_read_file(current_run_file_path, st.progress(0), st.empty())
        st.session_state.editor_content = content
        st.session_state.last_editor_content = None
        st.session_state.file_path = current_run_file_path
        st.session_state.file_origin = file_origin_for_run
        if uploaded_file:
            st.session_state.original_filename = uploaded_file.name
        else:
            st.session_state.original_filename = os.path.basename(local_path)
    st.success(f"Loaded '{st.session_state.original_filename}' into editor.")
    live_highlight()
    st.rerun()

st.subheader("📄 Text Editor")
editor_placeholder = """Welcome to Text Processing Pro!

1. Load a file using the panel on the left.
2. Enter a regex pattern.
3. See the matches highlight below in real-time.
4. Use the actions to capture, replace, or save your work.

You can also paste your own text directly into this editor."""
editor_content = st.session_state.get('editor_content')
if not editor_content:
    st.session_state.editor_content = editor_placeholder

st.text_area("Edit content below. Manual changes will be saved.", 
             height=400, key="editor_content", label_visibility="collapsed", on_change=live_highlight)

match_count = st.session_state.match_count
count_color = "green" if match_count > 0 else "gray"
st.markdown(f"#### 🔍 Live Results: <span style='color:{count_color};'>{match_count}</span> matches found", unsafe_allow_html=True)

with st.container(border=True, height=300):
    st.markdown(st.session_state.highlight_output, unsafe_allow_html=True)


if btn_capture:
    if not st.session_state.pattern_input:
        st.toast("⚠️ Enter a regex pattern to capture groups.")
    else:
        with st.expander("🎯 Captured Groups", expanded=True):
            try:
                text_content = st.session_state.get("editor_content", "")
                cp = compile_pattern(
                    st.session_state.pattern_input, 
                    st.session_state.case_sensitive_input,
                    st.session_state.multiline_input,
                    st.session_state.dotall_input
                )
                
                matches = cp.finditer(text_content)
                results = []
                num_groups = cp.groups
                
                for match in matches:
                    if num_groups > 0:
                        results.append(match.groups())
                    else:
                        results.append(match.group(0))

                if not results:
                    st.write("No matches found.")
                else:
                    if num_groups > 0 and isinstance(results[0], tuple):
                        df = pd.DataFrame(results, columns=[f"Group {i+1}" for i in range(num_groups)])
                        st.dataframe(df)
                        
                        @st.cache_data
                        def convert_df_to_csv(df):
                            return df.to_csv(index=False).encode('utf-8')
                        
                        csv = convert_df_to_csv(df)
                        st.download_button(
                            label="Download as CSV",
                            data=csv,
                            file_name="captured_groups.csv",
                            mime="text/csv",
                        )
                    else:
                        capture_text = "\n".join([str(res) for res in results])
                        st.text_area("Captured Data", value=capture_text, height=200, label_visibility="collapsed")

            except re.error as e:
                st.error(f"Invalid regex: {e}")

if 'btn_save_to_file' in locals() and btn_save_to_file:
    if not st.session_state.get("file_path"):
        st.warning("Could not find a file path. Please load a local file again.")
    else:
        with st.spinner("Saving file..."):
            content_to_save = st.session_state.editor_content
            success, result = save_editor_content_to_file(st.session_state.file_path, content_to_save)
            
            if success:
                st.session_state.last_backup = result
                st.success(f"File saved successfully. Backup created at: {result}")
            else:
                st.error(result)

if undo_file:
    backup_file = st.session_state.get("last_backup")
    if not backup_file or not os.path.exists(backup_file):
        st.info("No file backup is available to restore.")
    else:
        original_file = backup_file[:-4] if backup_file.endswith(".bak") else None
        if not original_file:
            st.error("Could not determine the original file path from the backup.")
        else:
            with st.expander(f"Confirm restoring backup for '{os.path.basename(original_file)}'"):
                st.write(f"This will overwrite '{original_file}' with the contents of '{backup_file}'.")
                if st.button("Confirm Restore", type="primary"):
                    try:
                        shutil.copy2(backup_file, original_file)
                        st.success(f"Restored backup to {original_file}")
                        st.session_state.last_backup = None
                    except Exception as e:
                        st.error(f"Failed to restore backup: {e}")

st.divider()
st.markdown("<div style='text-align: center; color: grey;'>Quick Regex Reference: . ^ $ * + ? { } [ ] \\ | ( )</div>", unsafe_allow_html=True)