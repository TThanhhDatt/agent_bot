import os
import smtplib
import traceback
from typing import Annotated
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from langgraph.types import Command
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from core.graph.state import AgentState
from core.utils.tool_function import build_update
from log.logger_config import setup_logging

load_dotenv()
logger = setup_logging(__name__)

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

@tool
def send_escalation_email_tool(
    issue_summary: Annotated[str, "Summary of the issue reported by the customer"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Use this tool to send an escalation email to the support team
    when a customer requests urgent assistance that requires immediate attention.
    Urgent issues may include service outages, critical account problems, or customer ask about refunds, discount.
    
    Args:
        issue_summary (str): Summary of the issue reported by the customer.
    """
    
    logger.info("Send escalation email called")
    
    customer_id = state["customer_id"]
    customer_name = state["name"] or "Chưa cung cấp"
    customer_phone = state["phone_number"] or "Chưa cung cấp"
    customer_address = state["address"] or "Chưa cung cấp"
    customer_email = state["email"] or "Chưa cung cấp"
    session_id = state["session_id"] or "Không lấy được"

    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, RECIPIENT_EMAIL]):
        logger.error("SMTP configuration is incomplete. Please check environment variables")
        raise ValueError("SMTP configuration is incomplete. Please check environment variables")

    try:
        subject = (
          f"🚨 Yêu Cầu Hỗ Trợ Khẩn Cấp Mới Từ Chatbot "
          f"- ID khách: {customer_id} | "
          f" Tên: {customer_name} | "
          f"Phiên: {session_id}"
        )

        html_template = """
        <!DOCTYPE html>
          <html lang="vi">
            <head>
              <meta charset="UTF-8" />
              <title>Yêu cầu hỗ trợ khẩn cấp</title>
            </head>
            <body style="margin:0; padding:0; background:#0f172a; font-family:Arial,Helvetica,sans-serif; color:#e6eef8;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0f172a; padding:20px;">
                <tr>
                  <td align="center">
                    <!-- Card -->
                    <table width="600" cellpadding="0" cellspacing="0" border="0" 
                           style="background:#111827; border-radius:12px; overflow:hidden; box-shadow:0 6px 18px rgba(0,0,0,0.5);">
                      <!-- Header -->
                      <tr>
                        <td style="background:linear-gradient(90deg,#ff6b6b,#7c5cff); padding:16px; text-align:center; color:#fff; font-size:20px; font-weight:bold;">
                          🚨 Yêu cầu hỗ trợ khẩn cấp mới
                        </td>
                      </tr>

                      <!-- Body -->
                      <tr>
                        <td style="padding:20px;">
                          <p style="margin:0 0 12px 0; font-size:15px; color:#9aa8c2;">
                            Ghi nhận và chuyển tới bộ phận CSKH — vui lòng phản hồi ngay.
                          </p>

                          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;">
                            <tr>
                              <td width="60" valign="top" align="center">
                                <div style="width:50px; height:50px; border-radius:8px; background:linear-gradient(135deg,#ff6b6b,#7c5cff); color:#0f172a; font-weight:bold; display:flex; align-items:center; justify-content:center; font-size:16px;">
                                  <p>
                                    {initials}
                                  </p>
                                </div>
                              </td>
                              <td valign="top" style="padding-left:12px; font-size:14px;">
                                <div><b>Khách hàng:</b> {customer_name}</div>
                                <div style="color:#9aa8c2; font-size:13px;"><b>SĐT:</b> {customer_phone}</div>
                                <div style="color:#9aa8c2; font-size:13px;"><b>Địa chỉ:</b> {customer_address}</div>
                                <div style="color:#9aa8c2; font-size:13px;"><b>Email khách:</b> {customer_email}</div>
                                <div style="color:#9aa8c2; font-size:13px;"><b>Thời gian:</b> {timestamp}</div>
                              </td>
                            </tr>
                          </table>

                          <div style="background:#1e293b; border:1px solid #334155; border-radius:8px; padding:12px; font-size:14px; color:#cbd5e1; line-height:1.5; margin-bottom:16px;">
                            <strong>Tóm tắt vấn đề:</strong>
                            <div style="margin-top:6px;">{issue_summary}</div>
                          </div>

                          <!-- Action Buttons -->
                          <table cellpadding="0" cellspacing="0" border="0" style="margin-bottom:20px;">
                            <tr>
                              <td>
                                <a href="{GOOGLE_SHEET_URL}" target="_blank"
                                   style="background:linear-gradient(90deg,#ff6b6b,#7c5cff); color:#0f172a; text-decoration:none; padding:10px 16px; border-radius:6px; font-weight:bold; font-size:14px; display:inline-block; margin-right:8px;">
                                  📑 Mở Google Sheet
                                </a>
                              </td>
                              <td>
                                <a href="tel:{customer_phone}"
                                   style="background:#1e293b; color:#e6eef8; text-decoration:none; padding:10px 16px; border-radius:6px; font-weight:bold; font-size:14px; display:inline-block; margin-right:8px;">
                                  📞 Gọi ngay
                                </a>
                              </td>
                              <td>
                                <a href="sms:{customer_phone}"
                                   style="background:#1e293b; color:#e6eef8; text-decoration:none; padding:10px 16px; border-radius:6px; font-weight:bold; font-size:14px; display:inline-block;">
                                  💬 Nhắn SMS
                                </a>
                              </td>
                            </tr>
                          </table>

                          <!-- Footer -->
                          <div style="font-size:12px; color:#94a3b8; text-align:center; border-top:1px solid #334155; padding-top:12px;">
                            Email này được gửi tự động từ hệ thống Chatbot Missi. Vui lòng không trả lời trực tiếp.
                          </div>
                        </td>
                      </tr>
                    </table>
                    <!-- End Card -->
                  </td>
                </tr>
              </table>
            </body>
          </html>
        """

        # Prepare safe replacement values        
        timestamp = datetime.now().strftime('%H:%M:%S - %d/%m/%Y')
        internal_note_val = ''
        issue_val = issue_summary or ''
        initials = 'KH'
        
        # Split name to get initials for avatar
        if customer_name:
            parts = [p for p in customer_name.split() if p]
            if parts:
                initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else ''))[:2].upper()

        # Replace placeholders used in the template. We replace exact literal tokens present
        html_body = html_template
        html_body = html_body.replace('{customer_phone}', customer_phone or '')
        html_body = html_body.replace('{customer_name}', customer_name or '')
        html_body = html_body.replace('{customer_address}', customer_address or '')
        html_body = html_body.replace('{customer_email}', customer_email or '')
        
        html_body = html_body.replace('{timestamp}', timestamp)
        html_body = html_body.replace('{internal_note}', internal_note_val)
        html_body = html_body.replace('{issue_summary}', issue_val)
        html_body = html_body.replace('{initials}', initials)

        # --- Thiết lập và gửi email ---
        msg = MIMEMultipart('alternative')
        msg['From'] = SMTP_USER
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        logger.success(f"Đã gửi email thông báo thành công đến {RECIPIENT_EMAIL}.")
        return Command(
          update=build_update(
                content="Has sent an escalation email to the support team.",
                tool_call_id=tool_call_id
            )
        )

    except Exception as e:
      error_details = traceback.format_exc()
      logger.error("Failed to send escalation email.")
      logger.error(error_details)
      
      return Command(
          update=build_update(
                content=f"Failed to send escalation email due to error: {str(e)}",
                tool_call_id=tool_call_id
            )
      )