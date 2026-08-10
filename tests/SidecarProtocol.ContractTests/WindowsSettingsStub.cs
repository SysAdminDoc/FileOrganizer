namespace Windows.Storage
{
    public sealed class ApplicationData
    {
        public static ApplicationData Current { get; } = new();
        public ApplicationDataContainer LocalSettings { get; } = new();
    }

    public sealed class ApplicationDataContainer
    {
        public IDictionary<string, object> Values { get; } =
            new Dictionary<string, object>(StringComparer.Ordinal);
    }
}

namespace Windows.Security.Credentials
{
    public sealed class PasswordCredential
    {
        public PasswordCredential(string resource, string userName, string password)
        {
            Resource = resource;
            UserName = userName;
            Password = password;
        }

        public string Resource { get; }
        public string UserName { get; }
        public string Password { get; }
        public void RetrievePassword() { }
    }

    public sealed class PasswordVault
    {
        private static readonly Dictionary<(string Resource, string UserName), string> Values = [];

        public void Add(PasswordCredential credential) =>
            Values[(credential.Resource, credential.UserName)] = credential.Password;

        public void Remove(PasswordCredential credential) =>
            Values.Remove((credential.Resource, credential.UserName));

        public PasswordCredential Retrieve(string resource, string userName) =>
            Values.TryGetValue((resource, userName), out var password)
                ? new PasswordCredential(resource, userName, password)
                : throw new InvalidOperationException("Credential not found.");
    }
}
