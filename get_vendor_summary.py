import sqlite3
import pandas as pd
import logging
import os
from ingestion_db import ingest_db

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Corrected logging setup
logging.basicConfig(
    filename='logs/get_vendor_summary.log',
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a"
)

def create_vendor_summary(conn):
    '''This table merges different tables to get the overall vendor summary and adds new columns in the result'''
    vendor_sales_summary = pd.read_sql_query("""
    WITH FreightSummary AS (
        SELECT VendorNumber, SUM(Freight) AS TotalFreightCost
        FROM vendor_invoice
        GROUP BY VendorNumber
    ),
    PurchaseSummary AS (
        SELECT
            p.VendorNumber,
            p.VendorName,
            p.Brand,
            p.Description,
            p.PurchasePrice,
            pp.Price AS ActualPrice,
            pp.Volume,
            SUM(p.Quantity) AS TotalPurchaseQuantity,
            SUM(p.Dollars) AS TotalPurchaseDollars
        FROM purchases p
        JOIN purchase_prices pp ON p.Brand = pp.Brand
        WHERE p.PurchasePrice > 0
        GROUP BY 
            p.VendorNumber,
            p.VendorName,
            p.Brand,
            p.Description,
            p.PurchasePrice,
            pp.Price,
            pp.Volume
    ),
    SalesSummary AS (
        SELECT
            VendorNo,
            Brand,
            SUM(SalesQuantity) AS TotalSalesQuantity,
            SUM(SalesDollars) AS TotalSalesDollars,
            SUM(SalesPrice) AS TotalSalesPrice,
            SUM(ExciseTax) AS TotalExciseTax
        FROM sales
        GROUP BY VendorNo, Brand
    )
    SELECT 
        ps.VendorName,
        ps.VendorNumber,
        ps.Brand,
        ps.PurchasePrice,
        ps.ActualPrice,
        ps.Volume,
        ps.TotalPurchaseQuantity,
        ps.TotalPurchaseDollars,
        ss.TotalSalesQuantity,
        ss.TotalSalesDollars,
        ss.TotalSalesPrice,
        ss.TotalExciseTax,
        fs.TotalFreightCost
    FROM PurchaseSummary ps
    LEFT JOIN SalesSummary ss ON ps.VendorNumber = ss.VendorNo AND ps.Brand = ss.Brand
    LEFT JOIN FreightSummary fs ON ps.VendorNumber = fs.VendorNumber
    ORDER BY ps.TotalPurchaseQuantity DESC;
    """, conn)
    return vendor_sales_summary

def clean_data(df):
    df['Volume'] = df['Volume'].astype('float64')

    # Fill missing values
    df.fillna(0, inplace=True)

    # Clean up strings
    df['VendorName'] = df['VendorName'].str.strip()
    df['Description'] = df['Description'].str.strip()

    # Derived columns
    df['GrossProfit'] = df['TotalSalesDollars'] - df['TotalPurchaseDollars']
    df['ProfitMargin'] = df['GrossProfit'] / df['TotalSalesDollars'].replace(0, 1)  # avoid div by zero
    df['Stockturnover'] = df['TotalSalesQuantity'] / df['TotalPurchaseQuantity'].replace(0, 1)
    df['SalestoPurchaseRatio'] = df['TotalSalesDollars'] / df['TotalPurchaseDollars'].replace(0, 1)

    return df

if __name__ == '__main__':
    conn = sqlite3.connect('inventory.db')

    logging.info('Creating Vendor Summary table...')
    summary_df = create_vendor_summary(conn)
    logging.info(summary_df.head().to_string())

    logging.info('Cleaning Data...')
    clean_df = clean_data(summary_df)
    logging.info(clean_df.head().to_string())

    logging.info('Ingesting data...')
    ingest_db(clean_df, 'vendor_sales_summary', conn)
    logging.info('Ingestion completed.')
