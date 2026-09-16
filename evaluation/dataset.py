test_snippets = [

    {
        "text": "def read_json_file(path): with open(path) as f: return json.load(f)",
        "file_path": "src/utils.py",
        "language": "python",
        "function_name": "read_json_file",
    },

    {
        "text": "def connect_to_postgres(host, port, db_name): return psycopg2.connect(host=host, port=port, dbname=db_name)",
        "file_path": "src/database.py",
        "language": "python",
        "function_name": "connect_to_postgres",
    },

    {
        "text": "def hash_password(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt())",
        "file_path": "src/auth.py",
        "language": "python",
        "function_name": "hash_password",
    },

    {
        "text": "def send_email(to, subject, body): smtp.sendmail(sender, to, message)",
        "file_path": "src/notifications.py",
        "language": "python",
        "function_name": "send_email",
    },

    {
        "text": "def calculate_average(numbers): return sum(numbers) / len(numbers)",
        "file_path": "src/math_utils.py",
        "language": "python",
        "function_name": "calculate_average",
    },

    {
        "text": "def resize_image(image, width, height): return image.resize((width, height))",
        "file_path": "src/image_utils.py",
        "language": "python",
        "function_name": "resize_image",
    },

    {
        "text": "def parse_csv(file_path): return pandas.read_csv(file_path)",
        "file_path": "src/data_loader.py",
        "language": "python",
        "function_name": "parse_csv",
    },

    {
        "text": "def validate_email(email): return re.match(r'^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+$', email)",
        "file_path": "src/validators.py",
        "language": "python",
        "function_name": "validate_email",
    },

]

test_queries = [
    {"query": "load data from a json file", "expected_function": "read_json_file"},
    {"query": "establish a database connection", "expected_function": "connect_to_postgres"},
    {"query": "encrypt a user password", "expected_function": "hash_password"},
    {"query": "send a notification email to a user", "expected_function": "send_email"},
    {"query": "compute the mean of a list of numbers", "expected_function": "calculate_average"},
    {"query": "scale an image to different dimensions", "expected_function": "resize_image"},
    {"query": "read data from a csv spreadsheet", "expected_function": "parse_csv"},
    {"query": "check if an email address is valid", "expected_function": "validate_email"},
]