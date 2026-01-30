from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'am-licita-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///am_licita.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelos
class OrdemServico(db.Model):
    __tablename__ = 'ordens_servico'
    
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(10), unique=True, nullable=False)
    cliente = db.Column(db.String(200), nullable=False)
    endereco = db.Column(db.String(300))
    cidade = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    cpf_cnpj = db.Column(db.String(20))
    email = db.Column(db.String(100))
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_conclusao = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pendente')  # pendente, concluida, cancelada
    observacoes = db.Column(db.Text)
    valor_total = db.Column(db.Float, default=0.0)
    itens = db.relationship('ItemOrdem', backref='ordem', lazy=True, cascade='all, delete-orphan')

class ItemOrdem(db.Model):
    __tablename__ = 'itens_ordem'
    
    id = db.Column(db.Integer, primary_key=True)
    ordem_id = db.Column(db.Integer, db.ForeignKey('ordens_servico.id'), nullable=False)
    descricao = db.Column(db.String(300), nullable=False)
    quantidade = db.Column(db.Float, default=1)
    valor_unitario = db.Column(db.Float, default=0.0)
    valor_total = db.Column(db.Float, default=0.0)

def gerar_numero_ordem():
    """Gera número da ordem no formato XX/AA"""
    ano = datetime.now().strftime('%y')
    ultima_ordem = OrdemServico.query.filter(
        OrdemServico.numero.like(f'%/{ano}')
    ).order_by(OrdemServico.id.desc()).first()
    
    if ultima_ordem:
        try:
            numero_atual = int(ultima_ordem.numero.split('/')[0])
            novo_numero = numero_atual + 1
        except:
            novo_numero = 1
    else:
        novo_numero = 1
    
    return f'{novo_numero:02d}/{ano}'

# Rotas
@app.route('/')
def index():
    """Dashboard principal"""
    busca = request.args.get('busca', '')
    status_filter = request.args.get('status', '')
    
    query = OrdemServico.query
    
    if busca:
        query = query.filter(
            db.or_(
                OrdemServico.cliente.ilike(f'%{busca}%'),
                OrdemServico.numero.ilike(f'%{busca}%')
            )
        )
    
    if status_filter:
        query = query.filter(OrdemServico.status == status_filter)
    
    ordens = query.order_by(OrdemServico.data_criacao.desc()).all()
    
    # Estatísticas
    total_ordens = OrdemServico.query.count()
    pendentes = OrdemServico.query.filter_by(status='pendente').count()
    concluidas = OrdemServico.query.filter_by(status='concluida').count()
    canceladas = OrdemServico.query.filter_by(status='cancelada').count()
    valor_total = db.session.query(db.func.sum(OrdemServico.valor_total)).scalar() or 0
    valor_pendente = db.session.query(
        db.func.sum(OrdemServico.valor_total)
    ).filter(OrdemServico.status == 'pendente').scalar() or 0
    
    stats = {
        'total': total_ordens,
        'pendentes': pendentes,
        'concluidas': concluidas,
        'canceladas': canceladas,
        'valor_total': valor_total,
        'valor_pendente': valor_pendente
    }
    
    return render_template('index.html', ordens=ordens, stats=stats, 
                          busca=busca, status_filter=status_filter)

@app.route('/ordem/nova', methods=['GET', 'POST'])
def nova_ordem():
    """Criar nova ordem de serviço"""
    if request.method == 'POST':
        try:
            ordem = OrdemServico(
                numero=gerar_numero_ordem(),
                cliente=request.form.get('cliente'),
                endereco=request.form.get('endereco'),
                cidade=request.form.get('cidade'),
                telefone=request.form.get('telefone'),
                cpf_cnpj=request.form.get('cpf_cnpj'),
                email=request.form.get('email'),
                observacoes=request.form.get('observacoes'),
                status='pendente'
            )
            
            db.session.add(ordem)
            db.session.flush()  # Para obter o ID
            
            # Processar itens
            itens_json = request.form.get('itens_json', '[]')
            itens = json.loads(itens_json)
            
            valor_total = 0
            for item in itens:
                novo_item = ItemOrdem(
                    ordem_id=ordem.id,
                    descricao=item['descricao'],
                    quantidade=float(item['quantidade']),
                    valor_unitario=float(item['valor_unitario']),
                    valor_total=float(item['quantidade']) * float(item['valor_unitario'])
                )
                valor_total += novo_item.valor_total
                db.session.add(novo_item)
            
            ordem.valor_total = valor_total
            db.session.commit()
            
            flash(f'Ordem de Serviço {ordem.numero} criada com sucesso!', 'success')
            return redirect(url_for('ver_ordem', id=ordem.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar ordem: {str(e)}', 'error')
            return redirect(url_for('nova_ordem'))
    
    return render_template('ordem_form.html', ordem=None)

@app.route('/ordem/<int:id>')
def ver_ordem(id):
    """Visualizar ordem de serviço"""
    ordem = OrdemServico.query.get_or_404(id)
    return render_template('ordem_view.html', ordem=ordem)

@app.route('/ordem/<int:id>/editar', methods=['GET', 'POST'])
def editar_ordem(id):
    """Editar ordem de serviço"""
    ordem = OrdemServico.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            ordem.cliente = request.form.get('cliente')
            ordem.endereco = request.form.get('endereco')
            ordem.cidade = request.form.get('cidade')
            ordem.telefone = request.form.get('telefone')
            ordem.cpf_cnpj = request.form.get('cpf_cnpj')
            ordem.email = request.form.get('email')
            ordem.observacoes = request.form.get('observacoes')
            
            # Remover itens antigos
            ItemOrdem.query.filter_by(ordem_id=ordem.id).delete()
            
            # Adicionar novos itens
            itens_json = request.form.get('itens_json', '[]')
            itens = json.loads(itens_json)
            
            valor_total = 0
            for item in itens:
                novo_item = ItemOrdem(
                    ordem_id=ordem.id,
                    descricao=item['descricao'],
                    quantidade=float(item['quantidade']),
                    valor_unitario=float(item['valor_unitario']),
                    valor_total=float(item['quantidade']) * float(item['valor_unitario'])
                )
                valor_total += novo_item.valor_total
                db.session.add(novo_item)
            
            ordem.valor_total = valor_total
            db.session.commit()
            
            flash(f'Ordem de Serviço {ordem.numero} atualizada com sucesso!', 'success')
            return redirect(url_for('ver_ordem', id=ordem.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar ordem: {str(e)}', 'error')
    
    return render_template('ordem_form.html', ordem=ordem)

@app.route('/ordem/<int:id>/status', methods=['POST'])
def alterar_status(id):
    """Alterar status da ordem"""
    ordem = OrdemServico.query.get_or_404(id)
    novo_status = request.form.get('status')
    
    if novo_status in ['pendente', 'concluida', 'cancelada']:
        ordem.status = novo_status
        if novo_status == 'concluida':
            ordem.data_conclusao = datetime.utcnow()
        db.session.commit()
        flash(f'Status alterado para {novo_status}!', 'success')
    
    return redirect(url_for('ver_ordem', id=ordem.id))

@app.route('/ordem/<int:id>/excluir', methods=['POST'])
def excluir_ordem(id):
    """Excluir ordem de serviço"""
    ordem = OrdemServico.query.get_or_404(id)
    numero = ordem.numero
    
    db.session.delete(ordem)
    db.session.commit()
    
    flash(f'Ordem de Serviço {numero} excluída!', 'success')
    return redirect(url_for('index'))

@app.route('/ordem/<int:id>/imprimir')
def imprimir_ordem(id):
    """Versão para impressão/PDF"""
    ordem = OrdemServico.query.get_or_404(id)
    return render_template('print.html', ordem=ordem)

@app.route('/api/estatisticas')
def api_estatisticas():
    """API para estatísticas em tempo real"""
    total = OrdemServico.query.count()
    pendentes = OrdemServico.query.filter_by(status='pendente').count()
    concluidas = OrdemServico.query.filter_by(status='concluida').count()
    valor_total = db.session.query(db.func.sum(OrdemServico.valor_total)).scalar() or 0
    
    return jsonify({
        'total': total,
        'pendentes': pendentes,
        'concluidas': concluidas,
        'valor_total': valor_total
    })

# Criar tabelas
with app.app_context():
    db.create_all()
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
