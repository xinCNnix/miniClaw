import { render, screen, waitFor } from "@testing-library/react"
import "@testing-library/jest-dom"
import MermaidRenderer from "./MermaidRenderer"

jest.mock("mermaid", () => ({
  initialize: jest.fn(),
  render: jest.fn(),
}))

import mermaid from "mermaid"

const mockedRender = mermaid.render as jest.MockedFunction<typeof mermaid.render>

describe("MermaidRenderer", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("renders SVG from valid Mermaid code", async () => {
    mockedRender.mockResolvedValue({ svg: "<svg><rect/></svg>" })

    render(<MermaidRenderer code="graph TD; A-->B" />)

    await waitFor(() => {
      expect(screen.container.innerHTML).toContain("<svg>")
    })
  })

  it("shows error state for invalid Mermaid code", async () => {
    mockedRender.mockRejectedValue(new Error("Parse error"))

    render(<MermaidRenderer code="invalid syntax" />)

    await waitFor(() => {
      expect(screen.getByText("Mermaid rendering failed")).toBeInTheDocument()
    })
  })

  it("shows loading state initially", () => {
    mockedRender.mockReturnValue(new Promise(() => {}))

    render(<MermaidRenderer code="graph TD; A-->B" />)

    expect(screen.getByText("Rendering diagram...")).toBeInTheDocument()
  })
})
