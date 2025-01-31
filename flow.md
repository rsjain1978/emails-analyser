graph TD
    A[Start] --> B[Generate 10 Emails]
    B --> C[Save Emails in MSG Format]
    C --> D{Parallel Analysis}
    D --> E[Analyze Email 1 for PII]
    D --> F[Analyze Email 2 for PII]
    D --> G[...]
    D --> H[Analyze Email 10 for PII]
    D --> I[Generate Overall Summary]
    E & F & G & H & I --> J[Display Results]
    J --> K[End]

    style A fill:#2D3748,stroke:#4A5568,stroke-width:2px,color:#fff
    style B fill:#2D3748,stroke:#4A5568,stroke-width:2px,color:#fff
    style C fill:#2D3748,stroke:#4A5568,stroke-width:2px,color:#fff
    style D fill:#2D3748,stroke:#4A5568,stroke-width:2px,color:#fff
    style J fill:#2D3748,stroke:#4A5568,stroke-width:2px,color:#fff
    style K fill:#2D3748,stroke:#4A5568,stroke-width:2px,color:#fff 