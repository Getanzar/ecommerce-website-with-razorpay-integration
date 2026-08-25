from io import BytesIO

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from reportlab.lib import colors


def generate_invoice(order):

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    story = []

    story.append(Paragraph("<b>Z I Y A</b>", styles["Title"]))
    story.append(Paragraph("Invoice", styles["Heading2"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph(f"Order ID : {order.id}", styles["Normal"]))
    story.append(Paragraph(f"Customer : {order.full_name}", styles["Normal"]))
    story.append(Paragraph(f"Phone : {order.phone}", styles["Normal"]))
    story.append(Paragraph(f"Payment : {order.payment_method}", styles["Normal"]))
    story.append(Paragraph(f"Status : {order.status}", styles["Normal"]))

    story.append(Spacer(1, 20))

    data = [
        [
            "Product",
            "Qty",
            "Price",
            "Subtotal",
        ]
    ]

    for item in order.items.all():

        data.append(
            [
                item.product_name,
                str(item.quantity),
                f"₹{item.price}",
                f"₹{item.subtotal}",
            ]
        )

    table = Table(data)

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0,0), (-1,0), colors.black),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 1, colors.grey),
                ("BOTTOMPADDING",(0,0),(-1,0),10),
            ]
        )
    )

    story.append(table)

    story.append(Spacer(1,20))

    financial = order.chargebreakdowns.first()
    if financial:
        summary = [
            ["Seller merchandise", f"₹{financial.merchant_subtotal}"],
            ["Platform fee", f"₹{financial.platform_fee}"],
            ["Product GST", f"₹{financial.merchandise_gst}"],
            ["GST on platform fee", f"₹{financial.platform_fee_gst}"],
            [f"{financial.delivery_mode.title()} delivery", f"₹{financial.delivery_fee}"],
            ["Delivery GST", f"₹{financial.delivery_gst}"],
            ["Seller-sponsored delivery", f"-₹{financial.seller_sponsored_delivery}"],
        ]
        summary_table = Table(summary, colWidths=[260, 120], hAlign="RIGHT")
        summary_table.setStyle(TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.lightgrey),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 12))

    story.append(
        Paragraph(
            f"<b>Total : ₹{order.total_price}</b>",
            styles["Heading2"],
        )
    )

    doc.build(story)

    pdf = buffer.getvalue()

    buffer.close()

    return pdf
