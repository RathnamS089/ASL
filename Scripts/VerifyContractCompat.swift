// Checks that the shared v1 response example still decodes with the iOS DTO.
// Compile with VisualiserCore/Sources/VisualiserCore/Translation.swift and run from the repository root.
import Foundation

@main
struct VerifyContractCompat {
    static func main() throws {
        let url = URL(fileURLWithPath: "contracts/examples/translation-response.json")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(TranslationResponse.self, from: Data(contentsOf: url)).validated()
        guard response.signs.count == 3, !response.isMock else {
            print("FAIL: unexpected decoded values")
            exit(1)
        }
        print("PASS: v1 translation-response.json decodes and validates with the iOS DTO")
    }
}
