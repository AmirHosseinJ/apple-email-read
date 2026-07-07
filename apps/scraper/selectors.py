# Flow Selectors
SIGN_IN_BUTTON = "a[aria-label='Sign in to Outlook']"
EMAIL_INPUT = "input[placeholder='Email, phone, or Skype']"
SUBMIT_NEXT_BUTTON = "input[type='submit']"
PASSWORD_INPUT = "#passwordEntry, input[type='password']"
GET_CODE_SIGN_IN_TITLE = "h1[data-testid='title']:has-text('Get a code to sign in')"
USE_PASSWORD_BUTTON = "span[role='button']:has-text('Use your password')"
SUBMIT_PASSWORD_BUTTON = '[data-testid="primaryButton"]'
STAY_SIGNED_IN_TITLE = "h1[data-testid='title']:has-text('Stay signed in?')"
STAY_SIGNED_IN_NO_BUTTON = "button[data-testid='secondaryButton']:has-text('No')"
OUTLOOK_SEARCH_INPUT = "input[aria-label*='Search'], input[placeholder*='Search'], [contenteditable='true'][aria-label*='Search']"
OUTLOOK_MESSAGE_ROW = "[role='option'], [role='listitem']"
SUBMIT_BACK_BUTTON = "#back-button"
RECOMMENDED_EMAIL_BUTTON = 'button[data-testid="suggestions"] button'

# BIRTHDAY
COUNTRY_NAME_SELECTOR="#countryDropdownId span[data-testid='truncatedSelectedText']"
BIRTHDAY_MONTH_DROPDOWN = "#BirthMonthDropdown"
BIRTHDAY_DAY_DROPDOWN = '#BirthDayDropdown'
BIRTHDAY_YEAR_INPUT = "input[name='BirthYear']"

# Add your name
FIRST_NAME_INPUT = "#firstNameInput"
LAST_NAME_INPUT = "#lastNameInput"

# Robot
ROBOT_FRAME0 = 'iframe[title="Human verification challenge"]'
ROBOT_FRAME = 'iframe[data-testid="humanCaptchaIframe"]'
ROBOT_ACCESSIBILITY_BUTTON = '[aria-label="Accessible challenge"]'
ROBOT_PRESS_AND_HOLD = 'div[role="button"]:has-text("Press and hold")'
ROBOT_PLEASE_WAIT = 'div[role="button"][aria-label="Please wait"]'
ROBOT_PRESS_AGAIN = 'div[role="button"]:has-text("Press again")'
ROBOT_TRY_AGAIN_MESSAGE = "text='Please try again'"

# ERROR Message
EMAIL_AVAILABILITY_MESSAGE_ERROR = 'div[role="alert"]:has-text("That username is already taken")'
WE_RAN_INTO_A_PROBLEM_MESSAGE_ERROR = 'h1[data-testid="title"]:has-text("We ran into a problem")'
ACCOUNT_CREATION_BLOCKED_MESSAGE_ERROR = 'h1[data-testid="title"]'
