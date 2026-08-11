# Flow Selectors
SIGN_IN_BUTTON = "a[aria-label='Sign in to Outlook']"
EMAIL_INPUT = "input[placeholder='Email, phone, or Skype']"
SUBMIT_NEXT_BUTTON = "input[type='submit']"
PASSWORD_INPUT = "#passwordEntry, input[type='password']"
INCORRECT_PASSWORD_ERROR = "[role='alert']:has-text('That password is incorrect for your Microsoft account.')"
GET_CODE_SIGN_IN_TITLE = (
    "h1[data-testid='title']:has-text('Get a code to sign in'), "
    "h1[data-testid='title']:has-text('Verify your email')"
)
USE_PASSWORD_BUTTON = "[data-testid='viewFooter'] span[role='button']:has-text('Use your password')"
SUBMIT_PASSWORD_BUTTON = '[data-testid="primaryButton"]'
STAY_SIGNED_IN_TITLE = "h1[data-testid='title']:has-text('Stay signed in?')"
STAY_SIGNED_IN_NO_BUTTON = "button[data-testid='secondaryButton']:has-text('No')"
PROTECT_ACCOUNT_TITLE = "#iPageTitle:has-text(\"Let's protect your account\")"
PROTECT_ACCOUNT_SKIP_BUTTON = "#iShowSkip, a:has-text('Skip for now')"
OUTLOOK_LAYOUT_DIALOG_TITLE = "[role='dialog']:has-text('Choose your Outlook layout')"
OUTLOOK_LAYOUT_MAILBOX_RECOMMENDED_BUTTON = (
    "[role='dialog']:has-text('Choose your Outlook layout') "
    "button:has-text('Mailbox (Recommended)')"
)
OUTLOOK_SEARCH_INPUT = "input[aria-label*='Search'], input[placeholder*='Search'], [contenteditable='true'][aria-label*='Search']"
OUTLOOK_MESSAGE_ROW = "[role='option'], [role='listitem']"
SUBMIT_BACK_BUTTON = "#back-button"
RECOMMENDED_EMAIL_BUTTON = 'button[data-testid="suggestions"] button'

HIGH_DEMAND_MESSAGE = "h1:has-text('Thank you for your patience')"


# Robot
ROBOT_FRAME0 = 'iframe[title="Human verification challenge"]'
ROBOT_FRAME = 'iframe[data-testid="humanCaptchaIframe"]'
ROBOT_ACCESSIBILITY_BUTTON = '[aria-label="Accessible challenge"]'
ROBOT_PRESS_AND_HOLD = 'div[role="button"]:has-text("Press and hold")'
ROBOT_PLEASE_WAIT = 'div[role="button"][aria-label="Please wait"]'
ROBOT_PRESS_AGAIN = 'div[role="button"]:has-text("Press again")'
ROBOT_TRY_AGAIN_MESSAGE = "text='Please try again'"
