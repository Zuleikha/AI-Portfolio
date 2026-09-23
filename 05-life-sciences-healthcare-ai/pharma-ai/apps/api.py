"""
Molecular Property Analyzer API
================================

FastAPI REST API for analyzing molecular properties and drug-likeness.

Endpoints:
- POST /analyze - Analyze a single molecule
- POST /batch - Analyze multiple molecules

Author: Zuleikha Khan
Date: 2026
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from molecular_property_analyzer import MolecularPropertyAnalyzer

# Initialize FastAPI app
app = FastAPI(
    title="Molecular Property Analyzer API",
    description="REST API for pharmaceutical property analysis and drug-likeness evaluation",
    version="1.0.0"
)

# Enable CORS for web applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize analyzer
analyzer = MolecularPropertyAnalyzer()


# Request/Response Models
class MoleculeRequest(BaseModel):
    """Request model for single molecule analysis"""
    smiles: str = Field(..., example="CC(=O)Oc1ccccc1C(=O)O", description="SMILES string of molecule")


class BatchRequest(BaseModel):
    """Request model for batch analysis"""
    smiles_list: List[str] = Field(
        ...,
        example=["CC(=O)Oc1ccccc1C(=O)O", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"],
        description="List of SMILES strings"
    )


class PropertyResponse(BaseModel):
    """Response model for molecular properties"""
    smiles: str
    properties: Dict[str, float]
    lipinski: Dict[str, Any]
    qed: float


class BatchResponse(BaseModel):
    """Response model for batch analysis"""
    results: List[PropertyResponse]
    total_analyzed: int
    total_druglike: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    message: str


# API Endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check"""
    return {
        "status": "online",
        "message": "Molecular Property Analyzer API is running"
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "API is operational"
    }


@app.post("/analyze", response_model=PropertyResponse)
async def analyze_molecule(request: MoleculeRequest):
    """
    Analyze a single molecule
    
    Args:
        request: MoleculeRequest with SMILES string
    
    Returns:
        PropertyResponse with molecular properties and drug-likeness
    
    Example:
        POST /analyze
        {
            "smiles": "CC(=O)Oc1ccccc1C(=O)O"
        }
    """
    try:
        # Analyze molecule
        result = analyzer.analyze_molecule(request.smiles)
        
        return PropertyResponse(
            smiles=result['SMILES'],
            properties=result['BasicProperties'],
            lipinski=result['Lipinski'],
            qed=result['QED']
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid SMILES string: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/batch", response_model=BatchResponse)
async def analyze_batch(request: BatchRequest):
    """
    Analyze multiple molecules in batch
    
    Args:
        request: BatchRequest with list of SMILES strings
    
    Returns:
        BatchResponse with analysis results for all molecules
    
    Example:
        POST /batch
        {
            "smiles_list": [
                "CC(=O)Oc1ccccc1C(=O)O",
                "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
            ]
        }
    """
    try:
        # Analyze batch
        df = analyzer.analyze_batch(request.smiles_list)
        
        # Convert DataFrame to list of results
        results = []
        for _, row in df.iterrows():
            results.append(PropertyResponse(
                smiles=row['SMILES'],
                properties={
                    'MolecularWeight': row['MolecularWeight'],
                    'LogP': row['LogP'],
                    'NumHDonors': row['NumHDonors'],
                    'NumHAcceptors': row['NumHAcceptors'],
                    'TPSA': row['TPSA'],
                    'NumRotatableBonds': row['NumRotatableBonds'],
                    'NumHeteroatoms': row['NumHeteroatoms'],
                    'NumAliphaticRings': row['NumAliphaticRings'],
                    'NumAromaticRings': row['NumAromaticRings'],
                    'QED': row['QED']
                },
                lipinski={
                    'LipinskiPass': row['LipinskiPass'],
                    'LipinskiViolations': row.get('LipinskiViolations', [])
                },
                qed=row['QED']
            ))
        
        # Calculate statistics
        total_druglike = df['LipinskiPass'].sum() if 'LipinskiPass' in df.columns else 0
        
        return BatchResponse(
            results=results,
            total_analyzed=len(results),
            total_druglike=int(total_druglike)
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch analysis failed: {str(e)}")


@app.get("/examples")
async def get_examples():
    """
    Get example SMILES strings for testing
    
    Returns:
        Dictionary of example drug molecules with their SMILES
    """
    examples = {
        "Aspirin": "CC(=O)Oc1ccccc1C(=O)O",
        "Ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "Caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
        "Paracetamol": "CC(=O)Nc1ccc(O)cc1",
        "Penicillin G": "CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O"
    }
    
    return {
        "examples": examples,
        "usage": "Use these SMILES strings to test the /analyze or /batch endpoints"
    }


if __name__ == "__main__":
    import uvicorn
    
    print("Starting Molecular Property Analyzer API...")
    print("API docs available at: http://localhost:8000/docs")
    print("Health check: http://localhost:8000/health")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)