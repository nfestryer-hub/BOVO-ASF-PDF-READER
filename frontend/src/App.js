import "@/App.css";
import { Toaster } from "sonner";
import TicketMaker from "@/pages/TicketMaker";

function App() {
  return (
    <div className="App">
      <TicketMaker />
      <Toaster position="top-center" richColors />
    </div>
  );
}

export default App;
