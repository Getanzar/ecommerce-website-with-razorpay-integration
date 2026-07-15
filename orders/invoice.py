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
                f"₹{item.subtotal()}",
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