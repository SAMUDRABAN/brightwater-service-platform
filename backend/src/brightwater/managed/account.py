"""Verified-account guidance shared by telephone and isolated evaluation tools."""


def identity_result(account):
    due = any(prop['obligations'] for prop in account['properties'])
    return {'verified': True, 'account': account, 'reminder_due': due,
        'instruction': ('Explain only the unresolved reminders actually returned, with their property and due date. Ask which work they want to arrange; do not select every property automatically.'
            if due else 'There are no unresolved reminders on this account. Do not say a service or certificate is due or invent a deadline. If the caller requests additional work, clarify its property and service before checking availability; otherwise explain briefly and close politely.')}
