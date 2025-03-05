import os
import io
import requests
from bs4 import BeautifulSoup
import pandas as pd
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from dotenv import load_dotenv
load_dotenv()

def parse_table(table):
    # Extract table headers
    headers = [th.text.strip() for th in table.find_all("th")]

    # Extract table rows
    rows = []
    for tr in table.find_all("tr")[1:]:  # Skip the header row
        cells = [td.text.strip() for td in tr.find_all("td")]
        rows.append(cells)

    df = pd.DataFrame(rows, columns=headers)
    return df

# Scrape the PnL and Balance Sheet data for a given company
def get_df(company_name):
    search_url = f"https://www.screener.in/api/company/search/?q={company_name}"
    search_response = session.get(search_url, headers=headers)
    search_results = search_response.json()

    if not search_results:
        print("Company not found!")
        exit()

    # Extract the first search result (assuming it's correct)
    company_slug = search_results[0]["url"]
    company_url = f"https://www.screener.in{company_slug}"

    response = requests.get(company_url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Locate the Profit & Loss table
    pnl_table = soup.find("section", {"id": "profit-loss"}).find("table", {"class": "data-table"})  # Locate the table
    pnl_df = parse_table(pnl_table)

    pnl_df.columns = ['Type'] + list(pnl_df.columns)[1:]
    pnl_df = pnl_df.filter(items=["Type", "Mar 2023", "Mar 2024"])

    bs_table = soup.find("section", {"id": "balance-sheet"}).find("table", {"class": "data-table"})  # Locate the table
    bs_df = parse_table(bs_table)

    bs_df.columns = ['Type'] + list(bs_df.columns)[1:]
    bs_df = bs_df.filter(items=["Type", "Mar 2023", "Mar 2024"])

    return pnl_df, bs_df

# Use LLM APIs to get the desired output
def get_result(df, user_prompt):

    df_string = df.to_string(index=False)

    llm = ChatGroq(
        temperature=0,
        model_name="llama-3.3-70b-versatile",
        groq_api_key=os.environ.get("GROQ_API_KEY")
    )

    prompt = ChatPromptTemplate.from_template(
        "Given the following DataFrame:\n{dataframe}\n\n{user_prompt}"
    )

    chain = (
        prompt 
        | llm 
        | StrOutputParser()
    )

    response = chain.invoke({
        "dataframe": df_string,
        "user_prompt": user_prompt
    })

    return response


session = requests.Session()

login_url = "https://www.screener.in/login/"
login_payload = {
    "username": os.environ.get("USERNAME"),
    "password": os.environ.get("PASSWORD")
}

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = session.post(login_url, data=login_payload, headers=headers)
if "Invalid username or password" in response.text:
    print("Login failed! Check your credentials.")
    exit()

pnl_prompt = "Using the Profit and Loss Dataframe provided, return only the following as csv (with type of value as row and year as column and every entry as a string), for March 23 and March 24: 1. Total Revenue 2. Total Expenses 3. Profit Before Tax 4. Net Profit. Just give me the csv, no code or anything else."
bs_prompt = "Using the Balance Sheet Dataframe provided, return only the following as csv (with type of value as row and year as column and every entry as a string), for March 23 and March 24: 1. Total Equity 2. Total Assets. Just give me the csv, no code or anything else."

pnl_dict = {}
bs_dict = {}

df = pd.read_excel("companies.xlsx")
for company_name in df["Companies"]:
    pnl_df, bs_df = get_df(company_name)
    pnl_result = get_result(pnl_df, pnl_prompt)
    bs_result = get_result(bs_df, bs_prompt)
    
    pnl_out_df = pd.read_csv(io.StringIO(pnl_result))
    bs_out_df = pd.read_csv(io.StringIO(bs_result))

    pnl_dict[company_name] = pnl_out_df
    bs_dict[company_name] = bs_out_df

# Write back the collected data to an Excel file
with pd.ExcelWriter("company_data.xlsx", engine="openpyxl") as writer:
    
    # Adding data in sheets
    for company in df["Companies"]:
        sheet_name = company
        df1 = pnl_dict[company]
        df2 = bs_dict[company]
        
        df1.to_excel(writer, sheet_name=sheet_name, startrow=2, index=False)
        df2.to_excel(writer, sheet_name=sheet_name, startrow=len(df1) + 2, index=False)

    # Adding compnay name to first row of each sheet
    workbook = writer.book
    for company in df["Companies"]:
        worksheet = workbook[company]
        worksheet.cell(row=1, column=1, value=f"{company} (values are in INR Crores)")




