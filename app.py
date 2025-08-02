import streamlit as st
import pandas as pd
import openai

# --- SETUP OPENAI CLIENT (v1.0+) ---
client = openai.OpenAI(api_key='YOUR_OPENAI_API_KEY')

st.title("Data Cleanliness Review App")

# 1. Upload a CSV
uploaded_file = st.file_uploader("Upload your FIDO/511 Mapping CSV", type=["csv"])
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.write("First 5 rows:", df.head())

    if "reviewed_rows" not in st.session_state:
        st.session_state.reviewed_rows = []
    if "current_row" not in st.session_state:
        st.session_state.current_row = 0

    total_rows = len(df)

    # 2. Row-by-row review
    if st.session_state.current_row < total_rows:
        row = df.iloc[st.session_state.current_row]

        st.subheader(f"Reviewing Row {st.session_state.current_row + 1} of {total_rows}")
        st.write(row)

        # --- AI Suggestion ---
        prompt = f"""
        Review this FIDO line for data cleanliness.
        Brand: {row.get('brand', '')}
        UPC: {row.get('UPC', '')}
        Description: {row.get('description', '')}
        Category: {row.get('category', '')}
        IS_DELETED: {row.get('IS_DELETED', '')}
        Is Brand ID Null?: {row.get('Is Brand ID Null?', '')}

        Tasks:
        - If this does NOT belong to the brand, say REMOVE.
        - If brand is wrong or missing, suggest the correct brand.
        - If category is not optimal, suggest a better category.
        - If description is inaccurate, suggest an improved one.
        - If row looks good, say KEEP and fill 'No Change' for category/brand/description.

        Format response as:
        Action: [KEEP/REMOVE]
        Updated Brand: [value]
        Updated Category: [value]
        Updated Description: [value]
        Reason: [explanation]
        """

        if st.button("Get AI Suggestion"):
            # Call OpenAI using the new v1+ client syntax
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}]
            )
            suggestion = response.choices[0].message.content

            # Basic parse (not bulletproof, just splits by key)
            def get_value(key):
                if key in suggestion:
                    return suggestion.split(f"{key}:")[1].split("\n")[0].strip()
                return ""

            action = st.text_input("Action", value=get_value("Action") or "KEEP")
            updated_brand = st.text_input("Updated Brand", value=get_value("Updated Brand") or row.get('brand', ''))
            updated_category = st.text_input("Updated Category", value=get_value("Updated Category") or row.get('category', ''))
            updated_desc = st.text_input("Updated Description", value=get_value("Updated Description") or row.get('description', ''))
            reason = st.text_area("Reason", value=get_value("Reason") or "")

            if st.button("Approve & Next"):
                reviewed = row.to_dict()
                reviewed.update({
                    "Action": action,
                    "Updated Brand": updated_brand,
                    "Updated Category": updated_category,
                    "Updated Description": updated_desc,
                    "Reason": reason
                })
                st.session_state.reviewed_rows.append(reviewed)
                st.session_state.current_row += 1
                st.experimental_rerun()
        else:
            # Set defaults for first pass
            st.text_input("Action", value="KEEP")
            st.text_input("Updated Brand", value=row.get('brand', ''))
            st.text_input("Updated Category", value=row.get('category', ''))
            st.text_input("Updated Description", value=row.get('description', ''))
            st.text_area("Reason", value="")
    else:
        # 3. Download cleaned CSV
        cleaned_df = pd.DataFrame(st.session_state.reviewed_rows)
        st.success("All rows reviewed!")
        st.dataframe(cleaned_df)
        st.download_button("Download Cleaned CSV", cleaned_df.to_csv(index=False), "cleaned_data.csv")
        # Reset for new uploads
        if st.button("Start Over"):
            st.session_state.reviewed_rows = []
            st.session_state.current_row = 0
            st.experimental_rerun()
else:
    st.info("Please upload a CSV to begin.")
