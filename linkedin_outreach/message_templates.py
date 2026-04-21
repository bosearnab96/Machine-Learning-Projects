"""Message copy for the three outreach surfaces.

The {first_name} placeholder is filled per-profile from the CSV.
"""

# ── DM sent AFTER a bare connection request is accepted (Option A, step 2) ──
# No character limit on DMs; we send the full pitch here.
FULL_MESSAGE_DM = """\
Hi {first_name},

Thanks for accepting! I'm Arnab from Meesho. I spent years scaling marketplace \
growth at Meesho — managing user activation, DAU retention, Mega Events & Sale \
Playbook and affiliate marketing across cohorts. I feel while the meta user \
growth playbooks would be the same between platforms and D2C websites, funnel \
improvement mental models are deeply different from D2C.

I'm actively learning D2C best practices right now, especially around user \
mental models. If you're open to a conversation about:

• Marketplace user segmentation frameworks (traffic channels, retention modeling)
• Conversion optimisation at scale (personalization, segmentation, homepage segregation)
• Industry patterns you've seen across brands

I'd love to exchange ideas. I can bring concrete marketplace-scale insights on \
funnel optimisation, cohort analysis, creator and content economy which might \
spark lateral thinking across D2C and platform mechanics.

Would a 20-min brief catch up work?

Cheers,
Arnab"""


# ── InMail to D2C heads (Option C, Premium) ─────────────────────────────────
# InMail has a subject line + 2000-char body limit. Full pitch fits.
INMAIL_SUBJECT = "Marketplace growth lessons → D2C — 20 min chat?"

INMAIL_BODY = """\
Hi {first_name},

I'm Arnab from Meesho. I spent years scaling marketplace growth at Meesho — \
managing user activation, DAU retention, Mega Events & Sale Playbook and \
affiliate marketing across cohorts. I feel while the meta user growth \
playbooks would be the same between platforms and D2C websites, funnel \
improvement mental models are deeply different from D2C.

I'm actively learning D2C best practices right now, especially around user \
mental models. If you're open to a conversation about:

• Marketplace user segmentation frameworks (traffic channels, retention modeling)
• Conversion optimisation at scale (personalization, segmentation, homepage segregation)
• Industry patterns you've seen across brands

I'd love to exchange ideas. I can bring concrete marketplace-scale insights on \
funnel optimisation, cohort analysis, creator and content economy which might \
spark lateral thinking across D2C and platform mechanics.

Would a 20-min brief catch up work?

Cheers,
Arnab"""


def render_dm(first_name: str) -> str:
    return FULL_MESSAGE_DM.format(first_name=first_name or "there")


def render_inmail(first_name: str) -> tuple[str, str]:
    return INMAIL_SUBJECT, INMAIL_BODY.format(first_name=first_name or "there")
